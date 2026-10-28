"""Live check against the real Lyria API. Each run costs about $0.04 (one Clip request).

Runs the real app pipeline (station preset -> prompt -> Lyria -> analysis -> recipe) and keeps
the result so a person can listen to it. Output goes to $AIMUSE_ARTIFACT_DIR when set (the
GitHub workflow uploads it as an artifact), otherwise to pytest's temp dir.

Skipped unless AIMUSE_LIVE=1 and GEMINI_API_KEY are set; on GitHub, start Backend CI by hand
with the "live" input ticked.
"""

import os
from pathlib import Path

import pytest

from aimuse.engines import LYRIA_PRICES_USD, LyriaEngine
from aimuse.pipeline import Budget, generate_track, rank, write_recipe
from aimuse.presets import load_style

pytestmark = pytest.mark.live


def _summary(track, style, out: Path) -> str:
    c = track.chosen_candidate
    a = c.analysis
    t = track.target
    lyrics = (out / c.lyrics_file).read_text() if c.lyrics_file else "(none returned)"
    return "\n".join(
        [
            f"# Live Lyria test: {style.name}",
            "",
            f"- Model: `{track.model}`, cost ≈ ${LYRIA_PRICES_USD[track.model]:.2f}",
            f"- Audio: `{c.file}` (in this run's artifact)",
            "",
            "| | Target | Measured |",
            "|---|---|---|",
            f"| Tempo | {t.bpm} BPM | {a.bpm} BPM |",
            f"| Key | {t.key} | {a.key} (confidence {a.key_confidence}) |",
            f"| Length | {t.duration_s} s | {a.duration_s} s |",
            f"| Loudness | – | {a.lufs} LUFS, peak {a.peak_dbfs} dBFS |",
            f"| Format | – | {a.sample_rate} Hz, {a.channels} ch |",
            "",
            f"QA issues: {'; '.join(c.qa.issues) if c.qa.issues else 'none'}",
            "",
            "## Prompt",
            "",
            "```",
            track.prompt_text,
            "```",
            "",
            "## Lyrics / structure returned by Lyria",
            "",
            "```",
            lyrics,
            "```",
            "",
        ]
    )


def test_lyria_clip_through_app_pipeline(tmp_path):
    out = Path(os.environ.get("AIMUSE_ARTIFACT_DIR") or tmp_path)
    style = load_style(os.environ.get("AIMUSE_LIVE_PRESET") or "rainy-morning-indie")
    # Clip always returns 30 s, so target 30 s to make the length check meaningful.
    intent = style.example_intents[0].model_copy(update={"duration_s": 30})
    engine = LyriaEngine(os.environ["GEMINI_API_KEY"], model="lyria-3-clip-preview")

    track = generate_track(
        engine,
        style,
        intent,
        name="live-clip",
        arm="live",
        out_dir=out,
        budget=Budget(engine.price_per_request_usd),
    )
    rank([track])
    write_recipe(track, style, out)

    cand = track.candidates[0]
    assert cand.error is None, cand.error
    c = track.chosen_candidate
    assert c is not None and (out / c.file).stat().st_size > 10_000
    (out / "live-summary.md").write_text(_summary(track, style, out))
    print(f"\n{(out / 'live-summary.md').read_text()}")

    a = c.analysis
    assert a.sample_rate == 44100 and a.channels == 2
    assert 20 <= a.duration_s <= 40  # Clip is documented as always 30 s
    assert a.silence_ratio < 0.5 and a.clipping_ratio <= 0.001
