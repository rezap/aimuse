"""Live checks against the real Lyria API. Each run costs about $0.04 (one Clip request).

Skipped unless AIMUSE_LIVE=1 and GEMINI_API_KEY are set; on GitHub, start Backend CI by hand
with the "live" input ticked.
"""

import os

import pytest

from aimuse.analysis import analyze, decode
from aimuse.engines import LyriaEngine
from aimuse.models import Intent, Vocals
from aimuse.prompt import compile_prompt

pytestmark = pytest.mark.live


def test_lyria_clip_generates_decodable_audio(style):
    engine = LyriaEngine(os.environ["GEMINI_API_KEY"], model="lyria-3-clip-preview")
    prompt = compile_prompt(style, Intent(vocals=Vocals.INSTRUMENTAL, duration_s=30))
    asset = engine.generate(prompt)

    assert asset.model == "lyria-3-clip-preview" and asset.cost_usd == 0.04
    assert len(asset.data) > 10_000
    y, sr = decode(asset.data)
    a = analyze(y, sr)
    summary = a.model_dump(exclude={"embedding", "spectrum_db"})
    print(f"\nmime={asset.mime_type} sr={sr} analysis={summary}")
    assert sr == 44100 and a.channels == 2
    assert 20 <= a.duration_s <= 40  # Clip is documented as always 30 s
    assert a.silence_ratio < 0.5
