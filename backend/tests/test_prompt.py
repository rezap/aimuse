import io

from PIL import Image

from aimuse.models import Intent, Vocals
from aimuse.presets import load_style
from aimuse.prompt import _scaled_structure, compile_prompt, returned_instrumental


def test_prompt_is_deterministic_and_complete(style):
    a = compile_prompt(style, Intent(theme="rain", energy=0.2))
    b = compile_prompt(style, Intent(theme="rain", energy=0.2))
    assert a.text == b.text
    assert "Tempo: 100 BPM." in a.text
    assert "Key: A minor." in a.text
    assert "sung lyrics, not an instrumental" in a.text
    assert "describe rain" in a.text
    assert "very calm" in a.text
    assert "[0:00 - 0:03] Intro" in a.text and "[0:03 - 0:10] Verse" in a.text
    assert a.images == []
    assert a.target.bpm == 100 and a.target.duration_s == 10


def test_intent_overrides_and_instrumental(style):
    p = compile_prompt(
        style, Intent(bpm=120, key="C major", vocals=Vocals.INSTRUMENTAL, duration_s=30)
    )
    assert "Tempo: 120 BPM." in p.text and "Key: C major." in p.text
    assert "Instrumental only, no vocals." in p.text
    assert "lyrics" not in p.text
    assert p.target.vocals == Vocals.INSTRUMENTAL and p.target.duration_s == 30


def test_anchor_image_is_stable_png(style):
    p1 = compile_prompt(style, Intent(), use_anchor_image=True)
    p2 = compile_prompt(style, Intent(label="other"), use_anchor_image=True)
    assert len(p1.images) == 1 and p1.images[0].mime_type == "image/png"
    assert p1.images[0].data == p2.images[0].data  # same station -> same image
    assert Image.open(io.BytesIO(p1.images[0].data)).size == (512, 512)


def test_structure_scales_to_duration(style):
    parts = _scaled_structure(style.structure, 95)
    assert parts[0][1] == 0 and parts[-1][2] == 95
    assert all(a[2] == b[1] for a, b in zip(parts, parts[1:], strict=False))


def test_vocals_on_instrumental_station_override_its_avoid_list_and_structure():
    lofi = load_style("late-night-lofi")
    assert "vocals" in lofi.avoid  # the station itself is instrumental
    p = compile_prompt(lofi, Intent(vocals=Vocals.VOCALS, theme="night buses"))
    avoid_line = next(line for line in p.text.splitlines() if line.startswith("Avoid:"))
    assert "vocal" not in avoid_line
    assert "Instrumental only" not in p.text
    assert "sung lyrics, not an instrumental" in p.text and "describe night buses" in p.text
    assert "] Verse 1" in p.text and "] Chorus" in p.text  # sung sections, not "Main groove"


def test_instrumental_on_vocal_station_avoids_vocals():
    p = compile_prompt(load_style("rainy-morning-indie"), Intent(vocals=Vocals.INSTRUMENTAL))
    assert "Instrumental only, no vocals." in p.text
    avoid_line = next(line for line in p.text.splitlines() if line.startswith("Avoid:"))
    assert avoid_line.endswith("vocals.") and "aggressive vocals" not in avoid_line
    assert "Vocals:" not in p.text


def test_returned_instrumental():
    assert returned_instrumental("<instrumental>") and returned_instrumental("  ")
    assert returned_instrumental(None) and returned_instrumental("[Instrumental]")
    assert not returned_instrumental("[Verse 1]\nRain on the glass")


KIPLING = """If you can keep your head when all about you
    Are losing theirs and blaming it on you,
If you can trust yourself when all men doubt you,
    But make allowance for their doubting too;

If you can dream—and not make dreams your master;
    If you can think—and not make thoughts your aim;
"""


def test_own_lyrics_are_sent_verbatim_with_verse_tags():
    from aimuse.prompt import format_user_lyrics

    formatted, sung = format_user_lyrics(KIPLING)
    assert sung == 6
    assert formatted.startswith("[Verse 1]\nIf you can keep your head when all about you\n")
    assert "\n\n[Verse 2]\nIf you can dream—and not make dreams your master;" in formatted

    p = compile_prompt(load_style("late-night-lofi"), Intent(lyrics=KIPLING))
    assert p.target.vocals == Vocals.VOCALS  # own lyrics are always sung
    assert p.target.duration_s == 60  # short text -> short song (min 60 s)
    assert p.text.endswith(formatted)
    assert "\nLyrics:\n[Verse 1]" in p.text
    assert "exactly as written" in p.text and "lyrics are original" not in p.text
    assert "Structure:" not in p.text  # the lyrics define the sections


def test_own_lyrics_keep_existing_tags_and_scale_length():
    from aimuse.prompt import duration_for_lyrics, format_user_lyrics

    formatted, sung = format_user_lyrics("[Chorus]\nla la\n\n[Verse]\nhey\r\nho")
    assert formatted == "[Chorus]\nla la\n\n[Verse]\nhey\nho" and sung == 3
    assert duration_for_lyrics(32) == 180 and duration_for_lyrics(15) == 110
