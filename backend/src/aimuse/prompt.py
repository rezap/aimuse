"""Prompt compiler: style bible + intent -> engine prompt.

Deterministic on purpose: the same style bible always produces the same wording, which is
one of the main levers for consistency across a station. Only the intent delta changes.
"""

from __future__ import annotations

import re

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


_TAG = re.compile(r"^\[[^\]]+\]$")


def format_user_lyrics(text: str) -> tuple[str, int]:
    """Tidy the listener's lyrics for Lyria; returns (lyrics, number of sung lines).

    Lyria's guide wants lyrics under a "Lyrics:" header with section tags. If the listener
    wrote no tags, each stanza (blank-line separated) becomes [Verse 1], [Verse 2], ...
    """
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    stanzas: list[list[str]] = [[]]
    for ln in lines:
        if ln:
            stanzas[-1].append(ln)
        elif stanzas[-1]:
            stanzas.append([])
    stanzas = [s for s in stanzas if s]
    has_tags = any(_TAG.match(ln) for s in stanzas for ln in s)
    out = []
    for i, stanza in enumerate(stanzas, 1):
        if not has_tags:
            out.append(f"[Verse {i}]")
        out.extend(stanza)
        out.append("")
    sung = sum(1 for s in stanzas for ln in s if not _TAG.match(ln))
    return "\n".join(out).strip(), sung


def duration_for_lyrics(sung_lines: int) -> int:
    """Roughly 6 s per sung line plus intro/outro, within what Lyria 3.5 makes (~3 min)."""
    return max(60, min(180, 20 + 6 * sung_lines))


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
    duration = intent.duration_s or style.duration_s
    vocals = intent.vocals or style.vocals
    if intent.lyrics and intent.lyrics.strip():
        vocals = Vocals.VOCALS  # own lyrics are meant to be sung
        if not intent.duration_s:
            duration = duration_for_lyrics(format_user_lyrics(intent.lyrics)[1])
    return TargetSpec(bpm=bpm, key=key, duration_s=duration, vocals=vocals)


def compile_prompt(
    style: StyleBible, intent: Intent, *, use_anchor_image: bool = False
) -> EnginePrompt:
    target = compile_target(style, intent)
    moods = [intent.mood] if intent.mood else style.moods

    sung = target.vocals == Vocals.VOCALS
    inf = intent.influences
    own_lyrics = format_user_lyrics(intent.lyrics)[0] if intent.lyrics else ""

    lines = [style.description.strip()]
    lines.append(f"Genre: {', '.join(style.genres)}.")
    if inf and not inf.is_empty():
        # The listener's artist reference, already translated into name-free traits.
        era = f" ({inf.era})" if inf.era else ""
        lines.append(f"Style influences: {', '.join(inf.genres)}{era}, blended with the above.")
    if sung:
        # Say it early and plainly: station descriptions can read as instrumental.
        lines.append("This is a song with a lead singer and sung lyrics, not an instrumental.")
    if moods:
        lines.append(f"Mood: {', '.join(moods)}.")
    if intent.energy is not None:
        lines.append(f"Energy: {_energy_words(intent.energy)}.")
    instruments = list(style.instruments)
    if inf:
        instruments += [i for i in inf.instrumentation if i not in instruments]
    if instruments:
        lines.append(f"Instrumentation: {', '.join(instruments)}.")
    lines.append(f"Tempo: {target.bpm} BPM.")
    if target.key:
        lines.append(f"Key: {target.key}.")
    production = [p for p in (style.production, inf.production if inf else None) if p]
    if production:
        lines.append(f"Production: {'; '.join(production)}.")

    if sung:
        theme = intent.theme or (style.lyric_themes[0] if style.lyric_themes else None)
        voice = (
            (inf.vocal_delivery if inf else None)
            or style.vocal_style
            or "warm, expressive lead vocal with light backing harmonies"
        )
        lines.append(f"Vocals: {voice}.")
        if own_lyrics:
            lines.append(
                "Sing the lyrics below exactly as written, in order. Do not add or change words."
            )
        else:
            about = f" and describe {theme}" if theme else ""
            lines.append(f"The lyrics are original, in {style.lyric_language}{about}.")
        if inf and inf.lyric_style:
            lines.append(f"Lyric style: {inf.lyric_style}.")
    else:
        lines.append("Instrumental only, no vocals.")

    if intent.text:
        lines.append(intent.text.strip())
    if inf:
        lines.append("Make it an original song; do not imitate any specific artist or song.")
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
    if own_lyrics:
        structure = []  # the listener's lyrics define the song's sections
    if structure:
        lines.append("Structure:")
        for name, start, end in _scaled_structure(structure, target.duration_s):
            lines.append(f"[{_timestamp(start)} - {_timestamp(end)}] {name}")

    if own_lyrics:
        lines.append("Lyrics:")
        lines.append(own_lyrics)

    images = []
    if use_anchor_image:
        lines.append("Let the mood and colours of the image shape the sound.")
        images.append(ImageInput(mime_type="image/png", data=anchor_image_png(style)))

    return EnginePrompt(text="\n".join(lines), images=images, target=target)
