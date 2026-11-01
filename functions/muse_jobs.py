"""Song job processing, independent of Firebase so it can be unit-tested.

Flow: the web app creates `users/{uid}/jobs/{jobId}` with status "queued" -> a Cloud Function
calls `process_job` -> the job is claimed (queued -> running, so duplicate trigger deliveries
are ignored) -> the daily budget is reserved -> the backend pipeline generates and analyses the
song -> audio goes to Storage, a track doc is written, the job becomes "done" (or "failed").
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from aimuse.engines import EngineError, MusicEngine
from aimuse.inspiration import MAX_REFERENCE_CHARS, InspirationError
from aimuse.models import Intent, Singer, StyleTraits, Vocals, VoiceTweaks
from aimuse.presets import load_style
from aimuse.prompt import singer_for, voice_description

MAX_THEME_CHARS = 200
MAX_LYRICS_CHARS = 3000
_REFUSAL_HINTS = ("safety", "block", "recitation", "copyright", "policy", "prohibit", "no audio")


def friendly_engine_error(message: str) -> str:
    """Explain refusals in plain words; keep the engine's own reason for reference."""
    if any(h in message.lower() for h in _REFUSAL_HINTS):
        return (
            "Lyria declined to make this song. Its filter refuses well-known or copyrighted "
            "lyrics (even famous public-domain poems) and named artists. Try your own words "
            f"or change the request. Details: {message[:200]}"
        )
    return message


class JobRequest(BaseModel):
    """What the web app may put in a job document."""

    station_id: str = Field(alias="stationId", min_length=1, max_length=64)
    mood: str | None = Field(default=None, max_length=40)
    theme: str | None = Field(default=None, max_length=MAX_THEME_CHARS)
    energy: float | None = Field(default=None, ge=0.0, le=1.0)
    vocals: bool | None = None
    singer: Literal["male", "female"] | None = None
    voice_tweaks: VoiceTweaks | None = Field(default=None, alias="voiceTweaks")
    inspiration: str | None = Field(default=None, max_length=MAX_REFERENCE_CHARS)
    lyrics: str | None = Field(default=None, max_length=MAX_LYRICS_CHARS)

    def to_intent(self, influences: StyleTraits | None = None) -> Intent:
        vocals = None
        if self.vocals is not None:
            vocals = Vocals.VOCALS if self.vocals else Vocals.INSTRUMENTAL
        theme = self.theme.strip() if self.theme and self.theme.strip() else None
        return Intent(
            label=theme or self.mood,
            mood=self.mood,
            theme=theme,
            energy=self.energy,
            vocals=vocals,
            singer=Singer(self.singer) if self.singer else None,
            voice_tweaks=self.voice_tweaks,
            influences=influences,
            lyrics=self.lyrics if self.lyrics and self.lyrics.strip() else None,
        )


class StyleTranslator(Protocol):
    def translate(self, reference: str) -> StyleTraits: ...


class JobStore(Protocol):
    def claim_job(self, uid: str, job_id: str) -> dict | None:
        """Atomically move a job from queued to running; return its data, or None if not queued."""

    def reserve_spend(self, uid: str, day: str, usd: float, cap_usd: float) -> bool:
        """Atomically add `usd` to the user's spend for `day` unless that would exceed the cap."""

    def complete_job(self, uid: str, job_id: str, track: dict) -> None:
        """Write the track doc (id = job id) and mark the job done."""

    def fail_job(self, uid: str, job_id: str, message: str) -> None: ...

    def get_influence(self, key: str) -> dict | None:
        """Cached traits for an artist reference (shared across users), or None."""

    def save_influence(self, key: str, reference: str, traits: dict) -> None: ...


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


# Bump when StyleTraits gains fields, so cached descriptions are made again (v2: singer, tempo;
# v3: detailed voice profile and era).
INFLUENCE_VERSION = "v3"


def reference_slug(reference: str) -> str:
    """ "Bob  DYLAN" and "bob dylan" are the same reference."""
    return re.sub(r"[^a-z0-9]+", "-", reference.lower()).strip("-")[:80]


def influence_key(reference: str) -> str:
    """Cache key for a reference's traits (versioned, see INFLUENCE_VERSION)."""
    slug = reference_slug(reference)
    return f"{INFLUENCE_VERSION}-{slug}" if slug else ""


def resolve_influences(
    reference: str, store: JobStore, translator_factory: Callable[[], StyleTranslator]
) -> StyleTraits:
    """Traits for a reference, translated once and then reused, so every song "like X" gets
    the same description (consistency) and the text model is called only once per artist."""
    key = influence_key(reference)
    if not key:
        raise InspirationError("empty reference")
    cached = store.get_influence(key)
    if cached:
        return StyleTraits.model_validate(cached)
    traits = translator_factory().translate(reference)
    store.save_influence(key, reference.strip(), traits.model_dump())
    return traits


def describe_reference(
    reference: str, store: JobStore, translator_factory: Callable[[], StyleTranslator]
) -> dict:
    """What an artist reference means, for the app to show before a song is made: the same
    (cached) traits the song will use. `key` names the listener's saved voice adjustments."""
    reference = reference.strip()
    if not reference or len(reference) > MAX_REFERENCE_CHARS:
        raise InspirationError("enter an artist or style of up to 80 characters")
    traits = resolve_influences(reference, store, translator_factory)
    singer = traits.singer if traits.singer and traits.singer != Singer.NONE else None
    return {
        "key": reference_slug(reference),
        "summary": traits.summary(),
        "era": traits.era,
        "singer": singer.value if singer else None,
        "voice": traits.voice_text(),
    }


def _title(req: JobRequest, station_name: str) -> str:
    first_line = next((ln.strip() for ln in (req.lyrics or "").splitlines() if ln.strip()), "")
    if first_line and not (req.theme and req.theme.strip()):
        return first_line[:60]
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
    is_allowed: Callable[[str], bool] = lambda uid: True,
    translator_factory: Callable[[], StyleTranslator] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    """Run one job. Returns the final status: "done", "failed" or "skipped"."""
    # Imported here: the audio stack is slow to load and only song generation needs it.
    from aimuse.pipeline import Budget, generate_track, rank

    job = store.claim_job(uid, job_id)
    if job is None:
        return "skipped"
    try:
        if not is_allowed(uid):
            raise JobFailed("This app is invite-only. Ask the owner to add your email address.")
        try:
            req = JobRequest.model_validate(job)
        except ValidationError as e:
            raise JobFailed(f"Invalid request: {e.errors()[0]['msg']}") from e
        try:
            style = load_style(req.station_id)
        except FileNotFoundError as e:
            raise JobFailed(f"Unknown station {req.station_id!r}") from e

        influences, inspiration_note = None, None
        reference = (req.inspiration or "").strip()
        if reference:
            try:
                if translator_factory is None:
                    raise InspirationError("artist styles are not enabled")
                influences = resolve_influences(reference, store, translator_factory)
            except InspirationError as e:
                # Not worth failing the song over: make it without the artist influence.
                inspiration_note = f"Made without the artist style ({e})."

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
                    req.to_intent(influences),
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
                raise JobFailed(
                    friendly_engine_error(errors[0]) if errors else "The engine returned no audio."
                )

            mime = "audio/mpeg" if cand.file.endswith(".mp3") else "audio/wav"
            path = f"users/{uid}/tracks/{job_id}.{_EXT.get(mime, 'bin')}"
            audio.upload(path, (out / cand.file).read_bytes(), mime)
            lyrics = (out / cand.lyrics_file).read_text() if cand.lyrics_file else None

        a = cand.analysis
        intent = req.to_intent(influences)
        sung = track.target.vocals == Vocals.VOCALS
        singer = singer_for(intent) if sung else None
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
                "inspiration": reference or None,
                "influences": influences.summary() if influences else None,
                "inspirationNote": inspiration_note,
                "ownLyrics": bool(req.lyrics and req.lyrics.strip()),
                "vocals": sung,
                "singer": singer.value if singer else None,
                "voice": voice_description(style, intent) if sung else None,
                # False when vocals were asked for but the engine made an instrumental.
                "vocalsDelivered": cand.vocals_ok,
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
