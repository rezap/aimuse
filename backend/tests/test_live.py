"""Live check against the real Lyria API. Each run costs about $0.04 (one Clip request).

Runs the real app pipeline (station preset -> prompt -> Lyria -> analysis -> recipe) and keeps
the result so a person can listen to it. Output goes to $AIMUSE_ARTIFACT_DIR when set (the
GitHub workflow uploads it as an artifact), otherwise to pytest's temp dir.

Skipped unless AIMUSE_LIVE=1 and GEMINI_API_KEY are set; on GitHub, start Backend CI by hand
with the "live" input ticked.
"""

import os
import re
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


# Vocal check: ask for vocals on every station, including the instrumental lo-fi station with the
# app's own model, and fail if Lyria answers "<instrumental>". About $0.20 per run.
VOCAL_CASES = [
    ("rainy-morning-indie", "lyria-3-clip-preview"),
    ("sunset-synthpop", "lyria-3-clip-preview"),
    ("late-night-lofi", "lyria-3-clip-preview"),
    ("late-night-lofi", "lyria-3.5"),
]


@pytest.mark.parametrize("station,model", VOCAL_CASES, ids=[f"{s}-{m}" for s, m in VOCAL_CASES])
def test_vocals_requested_are_sung(station, model, tmp_path):
    from aimuse.models import Vocals

    out = Path(os.environ.get("AIMUSE_ARTIFACT_DIR") or tmp_path) / "vocals"
    out.mkdir(parents=True, exist_ok=True)
    style = load_style(station)
    intent = style.example_intents[0].model_copy(update={"vocals": Vocals.VOCALS})
    if model == "lyria-3-clip-preview":
        intent = intent.model_copy(update={"duration_s": 30})
    engine = LyriaEngine(os.environ["GEMINI_API_KEY"], model=model)

    name = f"{station}-{model}"
    track = generate_track(
        engine,
        style,
        intent,
        name=name,
        arm="vocals",
        out_dir=out,
        budget=Budget(engine.price_per_request_usd),
    )
    rank([track])
    write_recipe(track, style, out)
    cand = track.candidates[0]
    assert cand.error is None, cand.error
    lyrics = (out / cand.lyrics_file).read_text() if cand.lyrics_file else ""
    with (out / "vocals-summary.md").open("a") as f:
        verdict = "✅ sung" if cand.vocals_ok else "❌ came out instrumental"
        first_lines = " / ".join(lyrics.strip().splitlines()[:3]) or "(no lyrics)"
        f.write(f"| {station} | `{model}` | {verdict} | `{cand.file}` | {first_lines} |\n")
    assert cand.vocals_ok, f"{name}: vocals requested but Lyria returned {lyrics.strip()[:80]!r}"


# Artist style: the real text model turns a reference into traits (including the singer's voice
# type), the name never reaches Lyria, and Lyria accepts the prompt (no safety block). Bob Dylan
# runs on the soft, breathy-voiced station on purpose: that combination came out with a female
# voice before the artist's traits led the prompt. Listen to the clips to judge the voice.
# "Bob Dylan 1997" checks that a period changes the description (era and voice). Each case's
# full description is saved next to its clip as <name>.traits.json.
# About $0.16 per run (4 clips + 4 tiny text calls).
ARTIST_CASES = [
    ("Bob Dylan", "rainy-morning-indie", "male"),
    ("Bob Dylan 1997", "rainy-morning-indie", "male"),
    ("Joni Mitchell", "rainy-morning-indie", "female"),
    ("Daft Punk", "sunset-synthpop", None),
]


@pytest.mark.parametrize(
    "reference,station,singer", ARTIST_CASES, ids=[r for r, _, _ in ARTIST_CASES]
)
def test_artist_style_is_described_not_named(reference, station, singer, tmp_path):
    from aimuse.inspiration import GeminiStyleTranslator, mentions_reference
    from aimuse.prompt import compile_prompt

    out = Path(os.environ.get("AIMUSE_ARTIST_DIR") or tmp_path) / "artist"
    out.mkdir(parents=True, exist_ok=True)
    key = os.environ["GEMINI_API_KEY"]
    traits = GeminiStyleTranslator(key).translate(reference)
    assert not traits.is_empty()
    assert not mentions_reference(traits.model_dump_json(), reference)

    from aimuse.models import Vocals

    style = load_style(station)
    intent = style.example_intents[0].model_copy(
        update={"duration_s": 30, "influences": traits, "vocals": Vocals.VOCALS}
    )
    prompt = compile_prompt(style, intent).text
    assert not mentions_reference(prompt, reference)
    engine = LyriaEngine(key, model="lyria-3-clip-preview")
    name = re.sub(r"\W+", "-", reference.lower())
    track = generate_track(
        engine,
        style,
        intent,
        name=name,
        arm="artist",
        out_dir=out,
        budget=Budget(engine.price_per_request_usd),
    )
    write_recipe(track, style, out)
    (out / f"{name}.traits.json").write_text(traits.model_dump_json(indent=2))
    cand = track.candidates[0]
    with (out / "artist-summary.md").open("a") as f:
        verdict = "✅" if cand.error is None else f"❌ {cand.error}"
        f.write(
            f"| {reference} | {station} | {traits.summary()} | {traits.singer or '–'}; "
            f"{traits.voice_text() or '–'} | {traits.bpm() or '–'} BPM | {verdict} | "
            f"`{cand.file}` |\n"
        )
    assert cand.error is None, cand.error
    if singer:
        assert traits.singer == singer, f"{reference}: expected a {singer} singer, got {traits}"
        assert f"with a {singer} lead singer" in prompt


# Own lyrics: does Lyria sing the listener's words? The original text must work. The famous poem
# ("If—", Kipling 1910, public domain) is recorded either way: it shows whether Lyria's
# recitation filter refuses well-known texts. About $0.08 per run (2 clips).
KIPLING_IF = """If you can keep your head when all about you
    Are losing theirs and blaming it on you,
If you can trust yourself when all men doubt you,
    But make allowance for their doubting too;

If you can dream—and not make dreams your master;
    If you can think—and not make thoughts your aim;
If you can meet with Triumph and Disaster
    And treat those two impostors just the same;"""
ORIGINAL_LYRICS = """Paper boats on a silver stream
Carry every little dream
Down the hill and past the mill
Where the morning air is still

[Chorus]
Let them sail, let them sail
Into the light beyond the rail"""
LYRICS_CASES = [("original", ORIGINAL_LYRICS, True), ("kipling-if", KIPLING_IF, False)]


@pytest.mark.parametrize("case,text,must_work", LYRICS_CASES, ids=[c for c, _, _ in LYRICS_CASES])
def test_own_lyrics(case, text, must_work, tmp_path):
    from aimuse.models import Intent

    out = Path(os.environ.get("AIMUSE_ARTIFACT_DIR") or tmp_path) / "lyrics"
    out.mkdir(parents=True, exist_ok=True)
    style = load_style("rainy-morning-indie")
    engine = LyriaEngine(os.environ["GEMINI_API_KEY"], model="lyria-3-clip-preview")
    track = generate_track(
        engine,
        style,
        Intent(lyrics=text, duration_s=30),
        name=case,
        arm="lyrics",
        out_dir=out,
        budget=Budget(engine.price_per_request_usd),
    )
    write_recipe(track, style, out)
    cand = track.candidates[0]
    sung = (out / cand.lyrics_file).read_text() if cand.lyrics_file else ""
    first = " / ".join(sung.strip().splitlines()[:2]) or "(none)"
    with (out / "lyrics-summary.md").open("a") as f:
        verdict = "✅ made" if cand.error is None else f"❌ {cand.error[:160]}"
        f.write(f"| {case} | {verdict} | {first} | `{cand.file}` |\n")
    if must_work:
        assert cand.error is None, cand.error
        assert cand.vocals_ok
