"""Generation pipeline: compile -> generate N candidates -> analyse -> QA -> rank -> write."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import soundfile as sf
from pydantic import BaseModel

from . import __version__
from .analysis import (
    QAResult,
    TrackAnalysis,
    analyze,
    check,
    decode,
    normalize_loudness,
    typicality,
)
from .engines.base import EngineError, MusicEngine
from .models import Intent, StyleBible, TargetSpec, Vocals
from .prompt import compile_prompt, returned_instrumental

_EXT = {"audio/mp3": "mp3", "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav"}


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    """Hard spending cap, checked before every paid request."""

    def __init__(self, max_usd: float):
        self.max_usd = max_usd
        self.spent_usd = 0.0
        self.requests = 0

    def charge(self, price_usd: float) -> None:
        if self.spent_usd + price_usd > self.max_usd + 1e-9:
            raise BudgetExceeded(
                f"next request (${price_usd:.2f}) would exceed the ${self.max_usd:.2f} cap "
                f"(spent ${self.spent_usd:.2f})"
            )
        self.spent_usd = round(self.spent_usd + price_usd, 4)
        self.requests += 1


class Candidate(BaseModel):
    index: int
    file: str | None = None
    lyrics_file: str | None = None
    analysis: TrackAnalysis | None = None
    qa: QAResult | None = None
    typicality: float | None = None
    vocals_ok: bool | None = None  # None when no vocals were requested
    score: float | None = None
    error: str | None = None


class TrackResult(BaseModel):
    name: str
    arm: str
    anchor_image: bool
    intent: Intent
    prompt_text: str
    target: TargetSpec
    engine: str
    model: str
    candidates: list[Candidate]
    chosen: int | None = None
    normalized_file: str | None = None
    normalize_gain_db: float | None = None

    @property
    def chosen_candidate(self) -> Candidate | None:
        return None if self.chosen is None else self.candidates[self.chosen]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "track"


def generate_track(
    engine: MusicEngine,
    style: StyleBible,
    intent: Intent,
    *,
    name: str,
    arm: str,
    out_dir: Path,
    budget: Budget,
    candidates: int = 1,
    use_anchor_image: bool = False,
) -> TrackResult:
    """Generate and analyse candidates for one track. Ranking happens later, per arm."""
    prompt = compile_prompt(style, intent, use_anchor_image=use_anchor_image)
    track_dir = out_dir / "tracks" / arm
    track_dir.mkdir(parents=True, exist_ok=True)
    result = TrackResult(
        name=name,
        arm=arm,
        anchor_image=use_anchor_image,
        intent=intent,
        prompt_text=prompt.text,
        target=prompt.target,
        engine=engine.id,
        model=engine.model,
        candidates=[],
    )
    for k in range(candidates):
        cand = Candidate(index=k)
        result.candidates.append(cand)
        budget.charge(engine.price_per_request_usd)  # raises BudgetExceeded before spending
        try:
            asset = engine.generate(prompt)
        except EngineError as e:
            cand.error = str(e)
            continue
        ext = _EXT.get(asset.mime_type, "bin")
        audio_path = track_dir / f"{name}_c{k}.{ext}"
        audio_path.write_bytes(asset.data)
        cand.file = str(audio_path.relative_to(out_dir))
        if prompt.target.vocals == Vocals.VOCALS:
            cand.vocals_ok = not returned_instrumental(asset.lyrics)
        if asset.lyrics:
            lyr = track_dir / f"{name}_c{k}.lyrics.txt"
            lyr.write_text(asset.lyrics)
            cand.lyrics_file = str(lyr.relative_to(out_dir))
        try:
            y, sr = decode(asset.data)
            cand.analysis = analyze(y, sr)
            cand.qa = check(cand.analysis, prompt.target)
            if cand.vocals_ok is False:
                cand.qa.issues.append("vocals requested but the engine returned an instrumental")
        except Exception as e:  # noqa: BLE001 - a bad file must not stop the batch
            cand.error = f"analysis failed: {e}"
    return result


def rank(tracks: list[TrackResult]) -> None:
    """Score every analysed candidate against the whole set and pick one per track."""
    reference = [
        c.analysis.embedding for t in tracks for c in t.candidates if c.analysis is not None
    ]
    for t in tracks:
        best, best_score = None, float("-inf")
        for c in t.candidates:
            if c.analysis is None or c.qa is None:
                continue
            c.typicality = typicality(c.analysis.embedding, reference)
            c.score = round(
                (1.0 if c.qa.passed else 0.0)
                + (0.5 if c.qa.bpm_ok else 0.0)
                + (0.5 if c.qa.key_ok else 0.0)
                + (1.0 if c.vocals_ok else 0.0)
                + c.typicality,
                4,
            )
            if c.score > best_score:
                best, best_score = c.index, c.score
        t.chosen = best


def write_normalized(track: TrackResult, out_dir: Path, target_lufs: float = -14.0) -> None:
    cand = track.chosen_candidate
    if cand is None or cand.file is None:
        return
    y, sr = decode((out_dir / cand.file).read_bytes())
    y_norm, gain = normalize_loudness(y, sr, target_lufs=target_lufs)
    path = (out_dir / cand.file).with_name(f"{track.name}.normalized.flac")
    sf.write(path, y_norm, sr, format="FLAC")
    track.normalized_file = str(path.relative_to(out_dir))
    track.normalize_gain_db = gain


def write_recipe(track: TrackResult, style: StyleBible, out_dir: Path) -> Path:
    """Everything needed to understand or regenerate this track."""
    recipe = {
        "aimuse_version": __version__,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "style": {"id": style.id, "version": style.version, "name": style.name},
        "license_note": (
            "AI-generated with Google Lyria via the Gemini API; contains a SynthID watermark. "
            "Commercial use not yet decided for AI Muse - personal use only."
        ),
        **track.model_dump(mode="json", exclude={"candidates"}),
        "candidates": [
            c.model_dump(mode="json", exclude={"analysis": {"embedding", "spectrum_db"}})
            for c in track.candidates
        ],
    }
    path = out_dir / "tracks" / track.arm / f"{track.name}.recipe.json"
    path.write_text(json.dumps(recipe, indent=2))
    return path
