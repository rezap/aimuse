"""Languages a song can be sung in, and how its lyrics are made.

Google documents vocals in eight languages for Lyria 3 (English, German, Spanish, French, Hindi,
Japanese, Korean, Portuguese). Others, such as Persian, are experimental: the app offers several
ways to get them sung so a listener can hear which works best.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class Language:
    code: str
    name: str  # as written in the prompt, e.g. "Persian (Farsi)"
    latin: bool  # written in Latin letters (so romanizing makes no sense)
    official: bool  # in Google's documented list of sung languages


LANGUAGES: dict[str, Language] = {
    lang.code: lang
    for lang in (
        Language("en", "English", latin=True, official=True),
        Language("es", "Spanish", latin=True, official=True),
        Language("fr", "French", latin=True, official=True),
        Language("de", "German", latin=True, official=True),
        Language("pt", "Portuguese", latin=True, official=True),
        Language("hi", "Hindi", latin=False, official=True),
        Language("ja", "Japanese", latin=False, official=True),
        Language("ko", "Korean", latin=False, official=True),
        Language("fa", "Persian (Farsi)", latin=False, official=False),
    )
}


def get_language(code: str | None) -> Language | None:
    if code is None:
        return None
    try:
        return LANGUAGES[code]
    except KeyError:
        raise ValueError(f"unknown language {code!r}") from None


class LyricsMode(StrEnum):
    """Who writes the words, and in which letters Lyria gets them."""

    LYRIA = "lyria"  # Lyria writes the lyrics in the language itself
    WRITTEN = "written"  # a Gemini text model writes them; Lyria sings them as given
    ROMANIZED = "romanized"  # written (or the listener's own), then sent in Latin letters


_ARABIC_SCRIPT = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_LATIN = re.compile(r"[A-Za-zÀ-ɏ]")


def script_of(text: str | None) -> str:
    """Rough script of a lyrics text: "Persian/Arabic", "Latin", "mixed" or "none"."""
    text = re.sub(r"\[[^\]]*\]", "", text or "")  # ignore [Verse] tags and timestamps
    arabic, latin = len(_ARABIC_SCRIPT.findall(text)), len(_LATIN.findall(text))
    if not arabic and not latin:
        return "none"
    if arabic and latin and min(arabic, latin) / max(arabic, latin) > 0.1:
        return "mixed"
    return "Persian/Arabic" if arabic > latin else "Latin"
