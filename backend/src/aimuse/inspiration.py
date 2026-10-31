"""Artist inspiration: turn "like Bob Dylan" into musical traits, never names.

Lyria blocks prompts that name artists or ask for their voice, and imitating a specific artist
is exactly what we don't want. So a listener's reference is translated by a text model into
neutral, descriptive traits (genre, era, instruments, production, vocal delivery and lyric style
in general terms). Only those traits reach the music engine; the name never does. As a second
line of defence, any word of the reference that leaks into the traits is removed.
"""

from __future__ import annotations

import json
import re

import httpx
from pydantic import ValidationError

from .engines.lyria import API_URL
from .models import Singer, StyleTraits

DEFAULT_MODEL = "gemini-3.8-flash"
MAX_REFERENCE_CHARS = 80

SYSTEM_INSTRUCTION = """\
You help a music app describe musical styles. The user names an artist, band or style they
like. Describe that style ONLY in general musical terms so a music generator can make an
original song in a similar spirit. The description replaces the app's own defaults, so be
specific about everything a listener would recognise: genre, era, who sings and how,
instruments, production and typical tempo.

Rules:
- Never write any proper noun: no artist, band, person, song, album, label or place names.
- Never quote or paraphrase lyrics. Never mention a specific song.
- singer: the voice type of the lead singer on most of their best-known recordings: "male",
  "female", "duet" (male and female leads) or "none" (instrumental act). For a style or genre
  rather than an artist, give the most typical voice type.
- vocal_delivery: register, texture and phrasing in generic terms (e.g. "nasal, reedy tenor,
  half-spoken phrasing"). Do not mention gender here, and never say it imitates or sounds like
  any person.
- bpm_min / bpm_max: the typical tempo range of their songs.
- avoid: 1-3 sounds that would make a song clearly NOT in this style.
- Keep each field short (a few words to one sentence).
- If the input is not a musician or musical style, or you are unsure, return empty genres.
"""

TRAITS_SCHEMA = {
    "type": "object",
    "properties": {
        "genres": {"type": "array", "items": {"type": "string"}, "description": "1-3 genres"},
        "era": {"type": "string", "description": "e.g. 'early 1960s'"},
        "instrumentation": {"type": "array", "items": {"type": "string"}},
        "production": {"type": "string"},
        "singer": {"type": "string", "enum": ["male", "female", "duet", "none"]},
        "vocal_delivery": {"type": "string"},
        "lyric_style": {"type": "string"},
        "bpm_min": {"type": "integer"},
        "bpm_max": {"type": "integer"},
        "avoid": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["genres", "instrumentation", "singer", "vocal_delivery", "bpm_min", "bpm_max"],
}

_STOPWORDS = {"the", "and", "band", "feat", "featuring", "with", "like", "style", "his", "her"}


class InspirationError(RuntimeError):
    """The reference could not be turned into usable traits."""


def _reference_words(reference: str) -> set[str]:
    words = re.findall(r"[\w']+", reference.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def scrub(traits: StyleTraits, reference: str) -> StyleTraits:
    """Remove any word of the reference (e.g. "Dylan") that leaked into the traits."""
    words = _reference_words(reference)
    if not words:
        return traits
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, sorted(words))) + r")\b", re.I)

    def clean(text: str | None) -> str | None:
        if text is None:
            return None
        out = re.sub(r"\s{2,}", " ", pattern.sub("", text)).strip(" ,;:-'\"")
        if all(w in _STOPWORDS for w in re.findall(r"[\w']+", out.lower())):
            return None  # nothing but filler left, e.g. "The" from "The Beatles"
        return out

    return traits.model_copy(
        update={
            "genres": [c for g in traits.genres if (c := clean(g))],
            "era": clean(traits.era),
            "instrumentation": [c for i in traits.instrumentation if (c := clean(i))],
            "production": clean(traits.production),
            "vocal_delivery": clean(traits.vocal_delivery),
            "lyric_style": clean(traits.lyric_style),
            "avoid": [c for a in traits.avoid if (c := clean(a))],
        }
    )


def mentions_reference(text: str, reference: str) -> bool:
    words = _reference_words(reference)
    return any(re.search(rf"\b{re.escape(w)}\b", text, re.I) for w in words)


class GeminiStyleTranslator:
    """Translates a reference with a Gemini text model (Interactions API, JSON output)."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        client: httpx.Client | None = None,
        timeout_s: float = 60.0,
    ):
        if not api_key:
            raise ValueError("a Gemini API key is required (set GEMINI_API_KEY)")
        self.model = model
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=timeout_s)

    def build_body(self, reference: str) -> dict:
        return {
            "model": self.model,
            "system_instruction": SYSTEM_INSTRUCTION,
            "input": f"Describe the musical style of: {reference}",
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": TRAITS_SCHEMA,
            },
        }

    def translate(self, reference: str) -> StyleTraits:
        reference = reference.strip()[:MAX_REFERENCE_CHARS]
        if not reference:
            raise InspirationError("empty reference")
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}
        try:
            resp = self._client.post(API_URL, json=self.build_body(reference), headers=headers)
        except httpx.TransportError as e:
            raise InspirationError(f"network error: {e}") from e
        if resp.status_code >= 400:
            raise InspirationError(f"style model error {resp.status_code}")
        text = "".join(
            block.get("text", "")
            for step in resp.json().get("steps", [])
            if step.get("type") == "model_output"
            for block in step.get("content", [])
            if block.get("type") == "text"
        )
        try:
            data = json.loads(text)
            # An implausible tempo shouldn't throw the whole description away.
            for k in ("bpm_min", "bpm_max"):
                if not isinstance(data.get(k), int) or not 40 <= data[k] <= 220:
                    data.pop(k, None)
            traits = StyleTraits.model_validate(data)
        except (ValueError, ValidationError, AttributeError) as e:
            raise InspirationError("style model returned unusable output") from e
        traits = scrub(traits, reference)
        if traits.is_empty():
            raise InspirationError("couldn't recognise that as a musical style")
        return traits


class FakeStyleTranslator:
    """Offline translator for tests and the emulator: fixed, name-free traits."""

    def __init__(self):
        self.calls = 0

    def translate(self, reference: str) -> StyleTraits:
        self.calls += 1
        if not reference.strip():
            raise InspirationError("empty reference")
        return StyleTraits(
            genres=["folk rock"],
            era="1960s",
            instrumentation=["acoustic guitar", "harmonica"],
            production="raw, live-in-the-room",
            singer=Singer.MALE,
            vocal_delivery="conversational, slightly rough storytelling vocal",
            lyric_style="poetic, story-driven lyrics",
            bpm_min=80,
            bpm_max=110,
            avoid=["polished studio pop"],
        )
