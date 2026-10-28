"""Prompt compiler: style bible + intent -> engine prompt.

Deterministic on purpose: the same style bible always produces the same wording, which is
one of the main levers for consistency across a station. Only the intent delta changes.
"""

from __future__ import annotations

from .anchor import anchor_image_png
from .models import EnginePrompt, ImageInput, Intent, Section, StyleBible, TargetSpec, Vocals


def _energy_words(energy: float) -> str:
    if energy < 0.25:
        return "very calm, sparse and gentle"
    if energy < 0.5:
        return "relaxed, laid-back"
    if energy < 0.75:
        return "steady, driving"
    return "high-energy, powerful"


def _timestamp(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def _scaled_structure(sections: list[Section], duration_s: int) -> list[tuple[str, int, int]]:
    """Scale the template's section lengths so they add up to the requested duration."""
    total = sum(s.seconds for s in sections)
    out, start = [], 0
    for i, s in enumerate(sections):
        if i == len(sections) - 1:
            end = duration_s
        else:
            end = start + max(1, round(s.seconds * duration_s / total))
        out.append((s.name, start, end))
        start = end
    return out


def compile_target(style: StyleBible, intent: Intent) -> TargetSpec:
    bpm = intent.bpm if intent.bpm is not None else round((style.bpm_min + style.bpm_max) / 2)
    key = intent.key or (style.keys[0] if style.keys else None)
    return TargetSpec(
        bpm=bpm,
        key=key,
        duration_s=intent.duration_s or style.duration_s,
        vocals=intent.vocals or style.vocals,
    )


def compile_prompt(
    style: StyleBible, intent: Intent, *, use_anchor_image: bool = False
) -> EnginePrompt:
    target = compile_target(style, intent)
    moods = [intent.mood] if intent.mood else style.moods

    lines = [style.description.strip()]
    lines.append(f"Genre: {', '.join(style.genres)}.")
    if moods:
        lines.append(f"Mood: {', '.join(moods)}.")
    if intent.energy is not None:
        lines.append(f"Energy: {_energy_words(intent.energy)}.")
    if style.instruments:
        lines.append(f"Instrumentation: {', '.join(style.instruments)}.")
    lines.append(f"Tempo: {target.bpm} BPM.")
    if target.key:
        lines.append(f"Key: {target.key}.")
    if style.production:
        lines.append(f"Production: {style.production}.")

    if target.vocals == Vocals.INSTRUMENTAL:
        lines.append("Instrumental only, no vocals.")
    else:
        theme = intent.theme or (style.lyric_themes[0] if style.lyric_themes else None)
        voice = style.vocal_style or "expressive lead vocals"
        about = f" about {theme}" if theme else ""
        lines.append(f"Vocals: {voice}, singing original {style.lyric_language} lyrics{about}.")

    if intent.text:
        lines.append(intent.text.strip())
    if style.avoid:
        lines.append(f"Avoid: {', '.join(style.avoid)}.")
    lines.append(f"Length: about {target.duration_s} seconds.")

    if style.structure:
        lines.append("Structure:")
        for name, start, end in _scaled_structure(style.structure, target.duration_s):
            lines.append(f"[{_timestamp(start)} - {_timestamp(end)}] {name}")

    images = []
    if use_anchor_image:
        lines.append("Let the mood and colours of the image shape the sound.")
        images.append(ImageInput(mime_type="image/png", data=anchor_image_png(style)))

    return EnginePrompt(text="\n".join(lines), images=images, target=target)
