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


# Used when vocals are requested but the station's structure has no sung sections
# (instrumental stations use "Main groove" / "Variation" etc.).
_SONG_STRUCTURE = [
    Section(name="Intro", seconds=8),
    Section(name="Verse 1", seconds=24),
    Section(name="Chorus", seconds=20),
    Section(name="Verse 2", seconds=24),
    Section(name="Chorus", seconds=20),
    Section(name="Outro", seconds=10),
]
_SUNG_SECTIONS = ("verse", "chorus", "hook", "bridge")


def _mentions_vocals(text: str) -> bool:
    t = text.lower()
    return "vocal" in t or "voice" in t or "singing" in t


def returned_instrumental(lyrics: str | None) -> bool:
    """Lyria answers with "<instrumental>" (or no lyrics) when it made no vocals."""
    if not lyrics or not lyrics.strip():
        return True
    return lyrics.strip().strip("<>[]() ").lower() in ("instrumental", "instrumental only")


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

    sung = target.vocals == Vocals.VOCALS

    lines = [style.description.strip()]
    lines.append(f"Genre: {', '.join(style.genres)}.")
    if sung:
        # Say it early and plainly: station descriptions can read as instrumental.
        lines.append("This is a song with a lead singer and sung lyrics, not an instrumental.")
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

    if sung:
        theme = intent.theme or (style.lyric_themes[0] if style.lyric_themes else None)
        voice = style.vocal_style or "warm, expressive lead vocal with light backing harmonies"
        lines.append(f"Vocals: {voice}.")
        about = f" and describe {theme}" if theme else ""
        lines.append(f"The lyrics are original, in {style.lyric_language}{about}.")
    else:
        lines.append("Instrumental only, no vocals.")

    if intent.text:
        lines.append(intent.text.strip())
    # The listener's vocals choice wins over the station's "avoid" list (e.g. "Avoid: vocals" on
    # an instrumental station when they asked for vocals).
    avoid = [a for a in style.avoid if not _mentions_vocals(a)]
    if not sung:
        avoid.append("vocals")
    if avoid:
        lines.append(f"Avoid: {', '.join(avoid)}.")
    lines.append(f"Length: about {target.duration_s} seconds.")

    structure = style.structure
    if sung and not any(s.name.lower().startswith(_SUNG_SECTIONS) for s in structure):
        structure = _SONG_STRUCTURE
    if structure:
        lines.append("Structure:")
        for name, start, end in _scaled_structure(structure, target.duration_s):
            lines.append(f"[{_timestamp(start)} - {_timestamp(end)}] {name}")

    images = []
    if use_anchor_image:
        lines.append("Let the mood and colours of the image shape the sound.")
        images.append(ImageInput(mime_type="image/png", data=anchor_image_png(style)))

    return EnginePrompt(text="\n".join(lines), images=images, target=target)
