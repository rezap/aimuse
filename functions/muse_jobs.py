"""Song job processing, independent of Firebase so it can be unit-tested.

Flow: the web app creates `users/{uid}/jobs/{jobId}` with status "queued" -> a Cloud Function
calls `process_job` -> the job is claimed (queued -> running, so duplicate trigger deliveries
are ignored) -> the daily budget is reserved -> the backend pipeline generates and analyses the
song -> audio goes to Storage, a track doc is written, the job becomes "done" (or "failed").
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

from aimuse.engines import EngineError, MusicEngine
from aimuse.models import Intent, Vocals
from aimuse.pipeline import Budget, generate_track, rank
from aimuse.presets import load_style

MAX_THEME_CHARS = 200


class JobRequest(BaseModel):
    """What the web app may put in a job document."""

    station_id: str = Field(alias="stationId", min_length=1, max_length=64)
    mood: str | None = Field(default=None, max_length=40)
    theme: str | None = Field(default=None, max_length=MAX_THEME_CHARS)
    energy: float | None = Field(default=None, ge=0.0, le=1.0)
    vocals: bool | None = None

    def to_intent(self) -> Intent:
        vocals = None
        if self.vocals is not None:
            vocals = Vocals.VOCALS if self.vocals else Vocals.INSTRUMENTAL
        theme = self.theme.strip() if self.theme and self.theme.strip() else None
        return Intent(
            label=theme or self.mood, mood=self.mood, theme=theme, energy=self.energy, vocals=vocals
        )


class JobStore(Protocol):
    def claim_job(self, uid: str, job_id: str) -> dict | None:
        """Atomically move a job from queued to running; return its data, or None if not queued."""

    def reserve_spend(self, uid: str, day: str, usd: float, cap_usd: float) -> bool:
        """Atomically add `usd` to the user's spend for `day` unless that would exceed the cap."""

    def complete_job(self, uid: str, job_id: str, track: dict) -> None:
        """Write the track doc (id = job id) and mark the job done."""

    def fail_job(self, uid: str, job_id: str, message: str) -> None: ...


class AudioStore(Protocol):
    def upload(self, path: str, data: bytes, content_type: str) -> None: ...


class JobFailed(Exception):
    """A failure whose message is safe and useful to show the listener."""


_EXT = {"audio/mp3": "mp3", "audio/mpeg": "mp3", "audio/wav": "wav"}


def display_bpm(measured: float | None, target: int) -> float | None:
    """Tempo detectors often report half or double time (e.g. 152 for a 76 BPM lo-fi beat).
    Show the octave of the measured tempo that is closest to what was asked for."""
    if not measured:
        return measured
    return round(min((measured * f for f in (0.5, 1.0, 2.0)), key=lambda b: abs(b - target)), 1)


def _title(req: JobRequest, station_name: str) -> str:
    if req.theme and req.theme.strip():
        t = req.theme.strip()
        return t[0].upper() + t[1:60]
    if req.mood:
        return f"{req.mood.capitalize()} {station_name.lower()}"
    return station_name


def process_job(
    uid: str,
    job_id: str,
    *,
    store: JobStore,
    audio: AudioStore,
    engine_factory: Callable[[], MusicEngine],
    daily_cap_usd: float,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    """Run one job. Returns the final status: "done", "failed" or "skipped"."""
    job = store.claim_job(uid, job_id)
    if job is None:
        return "skipped"
    try:
        try:
            req = JobRequest.model_validate(job)
        except ValidationError as e:
            raise JobFailed(f"Invalid request: {e.errors()[0]['msg']}") from e
        try:
            style = load_style(req.station_id)
        except FileNotFoundError as e:
            raise JobFailed(f"Unknown station {req.station_id!r}") from e

        engine = engine_factory()
        price = engine.price_per_request_usd
        if not store.reserve_spend(uid, now().strftime("%Y-%m-%d"), price, daily_cap_usd):
            raise JobFailed(f"Daily limit of ${daily_cap_usd:.2f} reached. Try again tomorrow.")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            try:
                track = generate_track(
                    engine,
                    style,
                    req.to_intent(),
                    name=job_id,
                    arm="app",
                    out_dir=out,
                    budget=Budget(price),
                )
            except EngineError as e:  # pragma: no cover - generate_track records these
                raise JobFailed(str(e)) from e
            rank([track])
            cand = track.chosen_candidate
            if cand is None or cand.file is None:
                errors = [c.error for c in track.candidates if c.error]
                raise JobFailed(errors[0] if errors else "The music engine returned no audio.")

            mime = "audio/mpeg" if cand.file.endswith(".mp3") else "audio/wav"
            path = f"users/{uid}/tracks/{job_id}.{_EXT.get(mime, 'bin')}"
            audio.upload(path, (out / cand.file).read_bytes(), mime)
            lyrics = (out / cand.lyrics_file).read_text() if cand.lyrics_file else None

        a = cand.analysis
        store.complete_job(
            uid,
            job_id,
            {
                "jobId": job_id,
                "stationId": style.id,
                "stationName": style.name,
                "title": _title(req, style.name),
                "mood": req.mood,
                "theme": req.theme,
                "energy": req.energy,
                "vocals": track.target.vocals == Vocals.VOCALS,
                "audioPath": path,
                "mimeType": mime,
                "durationS": a.duration_s if a else None,
                "bpm": display_bpm(a.bpm, track.target.bpm) if a else None,
                "key": a.key if a else None,
                "lufs": a.lufs if a else None,
                "targetBpm": track.target.bpm,
                "targetKey": track.target.key,
                "lyrics": lyrics,
                "prompt": track.prompt_text,
                "engine": track.engine,
                "model": track.model,
                "costUsd": price,
                "rating": 0,
            },
        )
        return "done"
    except JobFailed as e:
        store.fail_job(uid, job_id, str(e))
        return "failed"
    except Exception as e:  # noqa: BLE001 - never leave a job stuck in "running"
        store.fail_job(uid, job_id, f"Something went wrong ({type(e).__name__}). Please try again.")
        raise
