from __future__ import annotations

from typing import Protocol

from ..models import AudioAsset, EnginePrompt


class EngineError(RuntimeError):
    """A generation request failed (blocked prompt, API error, empty response...)."""


class MusicEngine(Protocol):
    id: str
    model: str

    @property
    def price_per_request_usd(self) -> float: ...

    def generate(self, prompt: EnginePrompt) -> AudioAsset: ...
