"""Domain models shared by the prompt compiler, engines, analysis and pipeline."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


class Vocals(StrEnum):
    VOCALS = "vocals"
    INSTRUMENTAL = "instrumental"


class Singer(StrEnum):
    """Who sings lead. A plain voice type, never a particular person's voice."""

    MALE = "male"
    FEMALE = "female"
    DUET = "duet"  # male and female
    NONE = "none"  # an instrumental act (only ever comes from an artist reference)


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


SINGER_WORDS = {
    Singer.MALE: "male lead singer",
    Singer.FEMALE: "female lead singer",
    Singer.DUET: "male and female singers",
}


class VoiceProfile(BaseModel):
    """What makes a voice recognisable, in generic words: the same *kind* of voice, never a
    particular person's. Each field is a short phrase; empty fields are left out."""

    voice_type: str | None = None  # register and range, e.g. "baritone, narrow range"
    texture: str | None = None  # e.g. "nasal, reedy, slightly raspy"
    delivery: str | None = None  # e.g. "half-spoken, drawled, words crammed into lines"
    pitch: str | None = None  # e.g. "loose, off-kilter pitch, no vibrato"
    character: str | None = None  # e.g. "weathered, older-sounding, American folk twang"
    recording: str | None = None  # e.g. "dry, close-miked, single take"
    backing: str | None = None  # e.g. "solo voice, no harmonies"

    def describe(self) -> str:
        fields = (self.voice_type, self.texture, self.delivery, self.pitch, self.character)
        parts = [f.strip() for f in fields if f and f.strip()]
        for extra in (self.recording, self.backing):
            if extra and extra.strip():
                parts.append(extra.strip())
        return "; ".join(parts)


_TWEAK_WORDS = {
    "pitch": ("sung low in the voice's range", "sung high in the voice's range"),
    "grit": ("smoother, cleaner tone", "rougher, grittier tone"),
    "spoken": ("fully sung, melodic phrasing", "more spoken, talk-sung phrasing"),
    "space": ("dry, close and intimate", "drenched in reverb"),
}


class VoiceTweaks(BaseModel):
    """The listener's nudges on top of a voice: -1, 0 or +1 each."""

    pitch: int = Field(default=0, ge=-1, le=1)  # lower / higher
    grit: int = Field(default=0, ge=-1, le=1)  # smoother / rougher
    spoken: int = Field(default=0, ge=-1, le=1)  # more sung / more spoken
    space: int = Field(default=0, ge=-1, le=1)  # drier / more reverb

    def describe(self) -> str:
        words = []
        for name, (down, up) in _TWEAK_WORDS.items():
            v = getattr(self, name)
            if v:
                words.append(up if v > 0 else down)
        return ", ".join(words)


class StyleTraits(BaseModel):
    """Musical traits of an artist/style the listener likes. Never contains names.

    An artist reference drives the song: its genres lead, its singer, vocal delivery,
    production and tempo replace the station's, and its instruments come first. The station
    still sets the mood, key and structure, and the listener's own choices win over both.
    """

    genres: list[str] = Field(default_factory=list)
    era: str | None = None
    instrumentation: list[str] = Field(default_factory=list)
    production: str | None = None
    singer: Singer | None = None
    vocal_delivery: str | None = None  # register, texture, phrasing; no gender (that's singer)
    voice: VoiceProfile | None = None  # the detailed version of vocal_delivery
    lyric_style: str | None = None
    bpm_min: int | None = Field(default=None, ge=40, le=220)
    bpm_max: int | None = Field(default=None, ge=40, le=220)
    avoid: list[str] = Field(default_factory=list)

    @field_validator("singer", mode="before")
    @classmethod
    def _known_singer(cls, v):
        # Text models occasionally answer outside the enum ("unknown", "group"); treat as unsaid.
        return v if v in {s.value for s in Singer} or isinstance(v, Singer) else None

    def voice_text(self) -> str | None:
        """The richest voice description available."""
        return (self.voice.describe() if self.voice else "") or self.vocal_delivery

    def bpm(self) -> int | None:
        """Typical tempo for this style, or None if the model didn't say."""
        lo, hi = self.bpm_min, self.bpm_max or self.bpm_min
        if lo is None:
            return hi
        return round((lo + max(lo, hi)) / 2)

    def summary(self) -> str:
        """One line for people (shown in the app next to the song)."""
        parts = [", ".join(self.genres)]
        if self.era:
            parts.append(self.era)
        if self.singer and self.singer != Singer.NONE:
            parts.append(SINGER_WORDS[self.singer])
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
    singer: Singer | None = None  # the listener's choice; wins over the artist reference
    voice_tweaks: VoiceTweaks | None = None
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
