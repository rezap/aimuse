"""Phase 0 experiment: how consistent is Lyria for one style bible, with vs without an anchor image?

Writes audio, lyrics, per-track recipes, `report.json` and `report.md` into the output dir.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from . import __version__
from .analysis import consistency
from .anchor import anchor_image_png
from .engines.base import MusicEngine
from .models import Intent, StyleBible
from .pipeline import (
    Budget,
    BudgetExceeded,
    TrackResult,
    generate_track,
    rank,
    slug,
    write_normalized,
    write_recipe,
)

ARMS = {"text": False, "image": True}  # arm name -> use anchor image
_HEAVY = {"analysis": {"embedding", "spectrum_db"}}  # large vectors kept out of JSON reports


class ArmSummary(BaseModel):
    arm: str
    tracks: int
    tracks_with_audio: int
    candidates_generated: int
    failed_requests: int
    qa_pass_rate: float | None
    bpm_adherence: float | None
    key_adherence: float | None
    consistency: float | None
    mean_lufs: float | None
    mean_duration_s: float | None


class SpikeReport(BaseModel):
    aimuse_version: str
    created_at: str
    engine: str
    model: str
    style_id: str
    style_name: str
    arms: list[str]
    candidates_per_track: int
    max_cost_usd: float
    spent_usd: float
    requests: int
    stopped_early: str | None
    summaries: list[ArmSummary]
    tracks: list[TrackResult]


def _rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def summarize(arm: str, tracks: list[TrackResult]) -> ArmSummary:
    chosen = [t.chosen_candidate for t in tracks if t.chosen_candidate is not None]
    analysed = [c for c in chosen if c.analysis and c.qa]
    keyed = [c.qa.key_ok for c in analysed if c.qa.key_ok is not None]
    cons = consistency([c.analysis.spectrum_db for c in analysed])
    return ArmSummary(
        arm=arm,
        tracks=len(tracks),
        tracks_with_audio=len(chosen),
        candidates_generated=sum(1 for t in tracks for c in t.candidates if c.file),
        failed_requests=sum(1 for t in tracks for c in t.candidates if c.error and not c.file),
        qa_pass_rate=_rate([c.qa.passed for c in analysed]),
        bpm_adherence=_rate([c.qa.bpm_ok for c in analysed]),
        key_adherence=_rate(keyed),
        consistency=None if math.isnan(cons) else cons,
        mean_lufs=_mean([c.analysis.lufs for c in analysed]),
        mean_duration_s=_mean([c.analysis.duration_s for c in analysed]),
    )


def pick_intents(style: StyleBible, n: int) -> list[Intent]:
    pool = style.example_intents or [Intent(label="default")]
    return [pool[i % len(pool)] for i in range(n)]


def run_spike(
    engine: MusicEngine,
    style: StyleBible,
    out_dir: Path,
    *,
    tracks: int = 4,
    candidates: int = 1,
    arms: list[str] | None = None,
    max_cost_usd: float = 1.0,
    normalize: bool = False,
) -> SpikeReport:
    arms = arms or list(ARMS)
    unknown = set(arms) - set(ARMS)
    if unknown:
        raise ValueError(f"unknown arms {sorted(unknown)}; choose from {sorted(ARMS)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    if any(ARMS[a] for a in arms):
        (out_dir / "anchor.png").write_bytes(anchor_image_png(style))

    budget = Budget(max_cost_usd)
    results: dict[str, list[TrackResult]] = {a: [] for a in arms}
    stopped = None
    try:
        # Interleave arms so a budget stop cuts both arms evenly.
        for i, intent in enumerate(pick_intents(style, tracks)):
            name = f"{i + 1:02d}-{slug(intent.label or intent.theme or 'track')}"
            for arm in arms:
                track = generate_track(
                    engine,
                    style,
                    intent,
                    name=name,
                    arm=arm,
                    out_dir=out_dir,
                    budget=budget,
                    candidates=candidates,
                    use_anchor_image=ARMS[arm],
                )
                results[arm].append(track)
    except BudgetExceeded as e:
        stopped = str(e)

    all_tracks = [t for a in arms for t in results[a]]
    rank(all_tracks)
    for t in all_tracks:
        if normalize:
            write_normalized(t, out_dir)
        write_recipe(t, style, out_dir)

    report = SpikeReport(
        aimuse_version=__version__,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        engine=engine.id,
        model=engine.model,
        style_id=style.id,
        style_name=style.name,
        arms=arms,
        candidates_per_track=candidates,
        max_cost_usd=max_cost_usd,
        spent_usd=budget.spent_usd,
        requests=budget.requests,
        stopped_early=stopped,
        summaries=[summarize(a, results[a]) for a in arms],
        tracks=all_tracks,
    )
    (out_dir / "report.json").write_text(
        json.dumps(
            report.model_dump(
                mode="json",
                exclude={"tracks": {"__all__": {"candidates": {"__all__": _HEAVY}}}},
            ),
            indent=2,
        )
    )
    (out_dir / "report.md").write_text(render_markdown(report))
    return report


def _fmt(v, pct=False):
    if v is None:
        return "–"
    return f"{v:.0%}" if pct else f"{v}"


def render_markdown(r: SpikeReport) -> str:
    lines = [
        f"# AI Muse spike: {r.style_name}",
        "",
        f"- Engine: `{r.engine}` / `{r.model}`",
        f"- Arms: {', '.join(r.arms)} (`image` = anchor image attached)",
        f"- Candidates per track: {r.candidates_per_track}",
        f"- Requests: {r.requests}, "
        f"estimated spend: ${r.spent_usd:.2f} of ${r.max_cost_usd:.2f} cap",
    ]
    if r.stopped_early:
        lines.append(f"- ⚠️ Stopped early: {r.stopped_early}")
    lines += [
        "",
        "## Summary",
        "",
        "| Arm | Tracks | With audio | Failed | QA pass | Tempo hit | Key hit | Consistency | "
        "Mean LUFS | Mean length (s) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in r.summaries:
        lines.append(
            f"| {s.arm} | {s.tracks} | {s.tracks_with_audio} | {s.failed_requests} | "
            f"{_fmt(s.qa_pass_rate, True)} | {_fmt(s.bpm_adherence, True)} | "
            f"{_fmt(s.key_adherence, True)} | {_fmt(s.consistency)} | {_fmt(s.mean_lufs)} | "
            f"{_fmt(s.mean_duration_s)} |"
        )
    lines += [
        "",
        "Consistency = mean pairwise correlation of the chosen tracks' average spectral shape "
        "(1.0 = identical sound). Tempo/key hit = measured tempo (half/double allowed) within 4% "
        "and key equal to the target or its relative major/minor.",
        "",
        "## Tracks",
        "",
        "| Track | Arm | Target | Measured | Score | File | Issues |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in r.tracks:
        c = t.chosen_candidate
        target = f"{t.target.bpm} BPM, {t.target.key or 'any key'}, {t.target.duration_s}s"
        if c is None or c.analysis is None:
            errors = "; ".join(x.error for x in t.candidates if x.error) or "no audio"
            lines.append(f"| {t.name} | {t.arm} | {target} | – | – | – | {errors} |")
            continue
        a = c.analysis
        measured = f"{a.bpm} BPM, {a.key}, {a.duration_s}s, {a.lufs} LUFS"
        issues = "; ".join(c.qa.issues) if c.qa and c.qa.issues else "none"
        lines.append(
            f"| {t.name} | {t.arm} | {target} | {measured} | {c.score} | `{c.file}` | {issues} |"
        )
    lines.append("")
    return "\n".join(lines)
