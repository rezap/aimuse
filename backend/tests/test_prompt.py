import io

from PIL import Image

from aimuse.models import Intent, Vocals
from aimuse.prompt import _scaled_structure, compile_prompt


def test_prompt_is_deterministic_and_complete(style):
    a = compile_prompt(style, Intent(theme="rain", energy=0.2))
    b = compile_prompt(style, Intent(theme="rain", energy=0.2))
    assert a.text == b.text
    assert "Tempo: 100 BPM." in a.text
    assert "Key: A minor." in a.text
    assert "lyrics about rain" in a.text
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
