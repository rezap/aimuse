"""Offline engine that synthesises simple audio matching the prompt's targets.

Used by tests and by the keyless CI smoke run: it exercises the full pipeline (analysis,
QA, ranking, reports, artifacts) without calling any paid API.
"""

from __future__ import annotations

import hashlib
import io

import numpy as np
import soundfile as sf

from ..models import AudioAsset, EnginePrompt, Key

SR = 22050


def _triad_freqs(key: Key) -> list[float]:
    third = 4 if key.mode == "major" else 3
    root_midi = 48 + key.pitch_class  # C3 + pitch class
    return [440.0 * 2 ** ((root_midi + iv - 69) / 12) for iv in (0, third, 7, 12)]


def synth_track(bpm: int, key: Key | None, seconds: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    if key is not None:
        for i, f in enumerate(_triad_freqs(key)):
            y += (0.12 / (1 + i)) * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi))
    # Percussive clicks on every beat give the tempo tracker something to lock on to.
    beat = 60.0 / bpm
    click_len = int(0.03 * SR)
    env = np.exp(-np.linspace(0, 8, click_len))
    for start in np.arange(0, seconds, beat):
        i = int(start * SR)
        seg = min(click_len, n - i)
        y[i : i + seg] += 0.6 * env[:seg] * rng.uniform(-1, 1, seg)
    y += rng.normal(0, 0.002, n)
    y /= max(1e-9, np.max(np.abs(y))) / 0.8
    return np.stack([y, y], axis=1).astype(np.float32)


class FakeEngine:
    id = "fake"

    def __init__(
        self, model: str = "fake-1", max_seconds: float | None = None, cost_usd: float = 0.0
    ):
        self.model = model
        self.max_seconds = max_seconds
        self._cost = cost_usd
        self.calls = 0

    @property
    def price_per_request_usd(self) -> float:
        return self._cost

    def generate(self, prompt: EnginePrompt) -> AudioAsset:
        self.calls += 1
        target = prompt.target
        key = Key.parse(target.key) if target.key else None
        seconds = float(target.duration_s)
        if self.max_seconds is not None:
            seconds = min(seconds, self.max_seconds)
        seed = int.from_bytes(hashlib.sha256(f"{prompt.text}:{self.calls}".encode()).digest()[:4])
        audio = synth_track(target.bpm, key, seconds, seed)
        buf = io.BytesIO()
        sf.write(buf, audio, SR, format="WAV", subtype="PCM_16")
        return AudioAsset(
            data=buf.getvalue(),
            mime_type="audio/wav",
            # Same markup as Lyria Clip, so the app's lyrics formatting is exercised offline.
            lyrics="[0.0:4.0] Fake engine sings softly\n[4.0:8.0] (la la la)",
            engine=self.id,
            model=self.model,
            cost_usd=self._cost,
        )
