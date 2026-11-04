"""Lyrics in other languages: written by a Gemini text model, optionally in Latin letters.

Lyria writes good lyrics in its documented languages, but for others (e.g. Persian) it may
mispronounce, drift into English, or refuse. Two alternatives let a listener compare:
- WRITTEN: a text model (strong in many more languages) writes the lyrics; Lyria only sings.
- ROMANIZED: the same lyrics, or the listener's own, are sent in Latin letters, which a music
  model trained mostly on Latin text may pronounce more reliably. The original script is kept
  for display.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

import httpx

from .engines.lyria import API_URL
from .languages import Language, LyricsMode, get_language
from .models import Intent, StyleBible

DEFAULT_MODEL = "gemini-3.8-flash"

WRITE_INSTRUCTION = """\
You write original song lyrics for a music app. Write in the requested language, in its normal
script, as a native songwriter would: natural, idiomatic, singable, with short lines.

Rules:
- Structure: [Verse 1], [Chorus], [Verse 2], [Chorus], each tag on its own line; 3-4 lines per
  section.
- Entirely original: never quote or adapt existing songs or poems, and use no names of real
  people, artists or brands.
- If romanization is requested, also give the same lyrics in Latin letters, line for line with
  the same tags, spelled so that a singer reading Latin letters pronounces the words correctly
  (a simple phonetic transliteration, not a translation).
"""

ROMANIZE_INSTRUCTION = """\
Transliterate song lyrics into Latin letters for a singer who reads Latin letters. Keep every
line and section tag ([Verse 1], [Chorus], ...) in place, one output line per input line. Spell
phonetically so the words are pronounced correctly; do not translate, add or drop words.
"""

LYRICS_SCHEMA = {
    "type": "object",
    "properties": {
        "lyrics": {"type": "string"},
        "romanized": {"type": "string"},
    },
    "required": ["lyrics"],
}
ROMANIZED_SCHEMA = {
    "type": "object",
    "properties": {"romanized": {"type": "string"}},
    "required": ["romanized"],
}


class LyricsError(RuntimeError):
    """The text model could not write or transliterate the lyrics."""


@dataclass
class WrittenLyrics:
    text: str  # in the language's own script
    romanized: str | None = None  # the same in Latin letters, when asked for


class LyricsWriter(Protocol):
    def write(self, language: Language, brief: str, *, romanize: bool = False) -> WrittenLyrics: ...

    def romanize(self, text: str, language: Language) -> str: ...


class GeminiLyricsWriter:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        client: httpx.Client | None = None,
        timeout_s: float = 90.0,
    ):
        if not api_key:
            raise ValueError("a Gemini API key is required (set GEMINI_API_KEY)")
        self.model = model
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=timeout_s)

    def _ask(self, system: str, text: str, schema: dict) -> dict:
        body = {
            "model": self.model,
            "system_instruction": system,
            "input": text,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
        }
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}
        try:
            resp = self._client.post(API_URL, json=body, headers=headers)
        except httpx.TransportError as e:
            raise LyricsError(f"network error: {e}") from e
        if resp.status_code >= 400:
            raise LyricsError(f"lyrics model error {resp.status_code}")
        out = "".join(
            block.get("text", "")
            for step in resp.json().get("steps", [])
            if step.get("type") == "model_output"
            for block in step.get("content", [])
            if block.get("type") == "text"
        )
        try:
            data = json.loads(out)
        except ValueError as e:
            raise LyricsError("lyrics model returned unusable output") from e
        if not isinstance(data, dict):
            raise LyricsError("lyrics model returned unusable output")
        return data

    def write(self, language: Language, brief: str, *, romanize: bool = False) -> WrittenLyrics:
        ask = f"Language: {language.name}.\nSong brief: {brief}"
        if romanize:
            ask += "\nAlso give the romanized version."
        data = self._ask(WRITE_INSTRUCTION, ask, LYRICS_SCHEMA)
        text = (data.get("lyrics") or "").strip()
        if not text:
            raise LyricsError("lyrics model returned no lyrics")
        romanized = (data.get("romanized") or "").strip() or None
        if romanize and not romanized:
            romanized = self.romanize(text, language)
        return WrittenLyrics(text=text, romanized=romanized)

    def romanize(self, text: str, language: Language) -> str:
        data = self._ask(
            ROMANIZE_INSTRUCTION, f"Language: {language.name}.\nLyrics:\n{text}", ROMANIZED_SCHEMA
        )
        out = (data.get("romanized") or "").strip()
        if not out:
            raise LyricsError("lyrics model returned no romanization")
        return out


_FAKE = {
    "fa": (
        "[Verse 1]\nباران آرام می‌بارد\nروی شیشه‌ی پنجره\n\n[Chorus]\nبمان با من امشب",
        "[Verse 1]\nbaaraan aaraam mibaarad\nrooye shisheye panjereh\n\n"
        "[Chorus]\nbemaan baa man emshab",
    ),
    "es": (
        "[Verse 1]\nLa lluvia cae despacio\nSobre el cristal\n\n[Chorus]\nQuédate conmigo",
        None,
    ),
}


class FakeLyricsWriter:
    """Offline writer for tests and the emulator."""

    def __init__(self):
        self.calls: list[str] = []

    def write(self, language: Language, brief: str, *, romanize: bool = False) -> WrittenLyrics:
        self.calls.append(f"write:{language.code}")
        text, roman = _FAKE.get(language.code, ("[Verse 1]\nla la la\n\n[Chorus]\nla la", None))
        return WrittenLyrics(text=text, romanized=(roman or text) if romanize else None)

    def romanize(self, text: str, language: Language) -> str:
        self.calls.append(f"romanize:{language.code}")
        known = _FAKE.get(language.code)
        return known[1] if known and known[1] and text == known[0] else f"(romanized) {text}"


@dataclass
class PreparedLyrics:
    intent: Intent  # what to send to the engine
    display: str | None = (
        None  # lyrics to show the listener (original script), if the app made them
    )
    mode: LyricsMode = LyricsMode.LYRIA


def lyrics_brief(style: StyleBible, intent: Intent) -> str:
    """What the song should be about, for the lyrics model."""
    theme = intent.theme or (style.lyric_themes[0] if style.lyric_themes else "a feeling")
    parts = [f"a {', '.join(style.genres)} song about {theme}"]
    if intent.mood:
        parts.append(f"mood: {intent.mood}")
    inf = intent.influences
    if inf and inf.lyric_style:
        parts.append(f"lyric style: {inf.lyric_style}")
    return "; ".join(parts)


def prepare_lyrics(
    style: StyleBible, intent: Intent, mode: LyricsMode | None, writer: LyricsWriter | None
) -> PreparedLyrics:
    """Apply the lyrics mode: have the words written and/or romanized before Lyria sings."""
    lang = get_language(intent.language)
    mode = mode or LyricsMode.LYRIA
    if mode == LyricsMode.ROMANIZED and lang and lang.latin:
        mode = LyricsMode.WRITTEN  # already Latin letters: nothing to romanize
    if lang is None or mode == LyricsMode.LYRIA:
        return PreparedLyrics(intent)
    if intent.lyrics and mode == LyricsMode.WRITTEN:
        return PreparedLyrics(intent)  # the listener wrote them: sing as written
    if writer is None:
        raise LyricsError("the lyrics writer is not enabled")

    if intent.lyrics:  # the listener's own words, sent in Latin letters
        romanized = writer.romanize(intent.lyrics, lang)
        sung = intent.model_copy(update={"lyrics": romanized[:3000], "lyrics_romanized": True})
        return PreparedLyrics(sung, display=intent.lyrics, mode=mode)

    written = writer.write(lang, lyrics_brief(style, intent), romanize=mode == LyricsMode.ROMANIZED)
    if mode == LyricsMode.ROMANIZED:
        sung = intent.model_copy(
            update={"lyrics": (written.romanized or "")[:3000], "lyrics_romanized": True}
        )
    else:
        sung = intent.model_copy(update={"lyrics": written.text[:3000]})
    return PreparedLyrics(sung, display=written.text, mode=mode)
