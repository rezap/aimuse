import pytest
from pydantic import ValidationError

from aimuse.models import Key, StyleBible
from aimuse.presets import list_presets, load_style


def test_key_parse_and_relative():
    k = Key.parse("Bb major")
    assert str(k) == "A# major"
    assert str(Key.parse("A minor").relative()) == "C major"
    assert str(Key.parse("C major").relative()) == "A minor"
    with pytest.raises(ValueError):
        Key.parse("H dorian")


def test_style_rejects_bad_key_and_bpm_order(style):
    data = style.model_dump()
    with pytest.raises(ValidationError):
        StyleBible.model_validate({**data, "keys": ["Q major"]})
    with pytest.raises(ValidationError):
        StyleBible.model_validate({**data, "bpm_min": 120, "bpm_max": 100})


def test_all_presets_load():
    names = list_presets()
    assert {"rainy-morning-indie", "late-night-lofi", "sunset-synthpop"} <= set(names)
    for name in names:
        s = load_style(name)
        assert s.id == name
        assert s.example_intents


def test_load_style_from_path(tmp_path, style):
    p = tmp_path / "mine.json"
    p.write_text(style.model_dump_json())
    assert load_style(str(p)).id == "test-station"
    with pytest.raises(FileNotFoundError):
        load_style("does-not-exist")
