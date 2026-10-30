"""Domain models shared by the prompt compiler, engines, analysis and pipeline."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


class Vocals(StrEnum):
    VOCALS = "vocals"
    INSTRUMENTAL = "instrumental"


class Key(BaseModel):
    """A musical key such as "A minor" or "F# major"."""

    tonic: str
    mode: str  # "major" | "minor"

    @classmethod
    def parse(cls, text: str) -> Key:
        parts = text.strip().split()
        if len(parts) != 2 or parts[1].lower() not in ("major", "minor"):
            raise ValueError(f"key must look like 'A minor' or 'C major', got {text!r}")
        tonic = parts[0][0].upper() + parts[0][1:]
        tonic = _FLAT_TO_SHARP.get(tonic, tonic)
        if tonic not in PITCH_CLASSES:
            raise ValueError(f"unknown tonic {parts[0]!r}")
        return cls(tonic=tonic, mode=parts[1].lower())

    @property
    def pitch_class(self) -> int:
        return PITCH_CLASSES.index(self.tonic)

    def relative(self) -> Key:
        """The relative major/minor, which shares the same notes."""
        if self.mode == "major":
            return Key(tonic=PITCH_CLASSES[(self.pitch_class + 9) % 12], mode="minor")
        return Key(tonic=PITCH_CLASSES[(self.pitch_class + 3) % 12], mode="major")

    def __str__(self) -> str:
        return f"{self.tonic} {self.mode}"


class Section(BaseModel):
    name: str
    seconds: int = Field(gt=0)


class StyleBible(BaseModel):
    """Frozen 'sound DNA' of a station or album. Every track in it is compiled from this."""

    id: str
    name: str
    version: int = 1
    description: str
    genres: list[str]
    moods: list[str] = []
    instruments: list[str] = []
    bpm_min: int = Field(ge=40, le=220)
    bpm_max: int = Field(ge=40, le=220)
    keys: list[str] = []
    vocals: Vocals = Vocals.VOCALS
    vocal_style: str | None = None
    lyric_language: str = "English"
    lyric_themes: list[str] = []
    production: str | None = None
    structure: list[Section] = []
    duration_s: int = Field(default=120, ge=10, le=240)
    palette: list[str] = []  # hex colours for the anchor image
    avoid: list[str] = []
    example_intents: list[Intent] = []

    @field_validator("keys")
    @classmethod
    def _valid_keys(cls, v: list[str]) -> list[str]:
        for k in v:
            Key.parse(k)
        return v

    @model_validator(mode="after")
    def _bpm_order(self) -> StyleBible:
        if self.bpm_min > self.bpm_max:
            raise ValueError("bpm_min must be <= bpm_max")
        return self


class StyleTraits(BaseModel):
    """Musical traits of an artist/style the listener likes. Never contains names."""

    genres: list[str] = Field(default_factory=list)
    era: str | None = None
    instrumentation: list[str] = Field(default_factory=list)
    production: str | None = None
    vocal_delivery: str | None = None
    lyric_style: str | None = None

    def summary(self) -> str:
        """One line for people (shown in the app next to the song)."""
        parts = [", ".join(self.genres)]
        if self.era:
            parts.append(self.era)
        if self.instrumentation:
            parts.append(", ".join(self.instrumentation[:4]))
        return " · ".join(p for p in parts if p)

    def is_empty(self) -> bool:
        return not self.genres and not self.instrumentation


class Intent(BaseModel):
    """What the listener wants from one track, on top of the style bible."""

    label: str | None = None
    text: str | None = None
    mood: str | None = None
    theme: str | None = None
    energy: float | None = Field(default=None, ge=0.0, le=1.0)
    bpm: int | None = Field(default=None, ge=40, le=220)
    key: str | None = None
    vocals: Vocals | None = None
    duration_s: int | None = Field(default=None, ge=10, le=240)
    influences: StyleTraits | None = None
    lyrics: str | None = Field(default=None, max_length=3000)  # the listener's own words

    @field_validator("key")
    @classmethod
    def _valid_key(cls, v: str | None) -> str | None:
        if v is not None:
            Key.parse(v)
        return v


StyleBible.model_rebuild()


class TargetSpec(BaseModel):
    """Measurable targets a generated track is checked against."""

    bpm: int
    key: str | None
    duration_s: int
    vocals: Vocals


class ImageInput(BaseModel):
    mime_type: str
    data: bytes


class EnginePrompt(BaseModel):
    text: str
    images: list[ImageInput] = []
    target: TargetSpec


class AudioAsset(BaseModel):
    data: bytes
    mime_type: str
    lyrics: str | None = None
    engine: str
    model: str
    cost_usd: float = 0.0
