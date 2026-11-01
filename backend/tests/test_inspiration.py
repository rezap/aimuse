import json

import httpx
import pytest

from aimuse.inspiration import (
    FakeStyleTranslator,
    GeminiStyleTranslator,
    InspirationError,
    mentions_reference,
    scrub,
)
from aimuse.models import Intent, Singer, StyleTraits, Vocals, VoiceTweaks
from aimuse.presets import load_style
from aimuse.prompt import compile_prompt


def _reply(payload):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {"steps": [{"type": "model_output", "content": [{"type": "text", "text": text}]}]}


def _translator(handler):
    return GeminiStyleTranslator("k", client=httpx.Client(transport=httpx.MockTransport(handler)))


GOOD = {
    "genres": ["folk rock"],
    "era": "early 1960s",
    "instrumentation": ["acoustic guitar", "harmonica"],
    "production": "sparse, live",
    "vocal_delivery": "nasal, conversational storytelling vocal",
    "lyric_style": "poetic protest songs",
    "singer": "male",
    "bpm_min": 90,
    "bpm_max": 120,
    "avoid": ["glossy pop production"],
    "voice": {
        "voice_type": "tenor, narrow range",
        "texture": "nasal, reedy",
        "delivery": "half-spoken, drawled",
        "pitch": "loose, no vibrato",
        "character": "young, wry",
    },
}


def test_translate_request_and_parse():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_reply(GOOD))

    traits = _translator(handler).translate("  Bob Dylan ")
    body = seen["body"]
    assert body["model"] == "gemini-3.8-flash"
    assert "Never write any proper noun" in body["system_instruction"]
    assert body["response_format"]["mime_type"] == "application/json"
    assert body["input"].endswith("Bob Dylan")
    assert traits.genres == ["folk rock"] and "harmonica" in traits.instrumentation
    assert "singer" in body["response_format"]["schema"]["required"]
    assert traits.singer == "male" and traits.bpm() == 105
    assert traits.summary() == (
        "folk rock · early 1960s · male lead singer · acoustic guitar, harmonica"
    )


def test_odd_singer_or_tempo_answers_are_dropped_not_fatal():
    odd = {**GOOD, "singer": "unknown", "bpm_min": 5, "bpm_max": "fast"}
    traits = _translator(lambda r: httpx.Response(200, json=_reply(odd))).translate("x band")
    assert traits.singer is None and traits.bpm() is None and traits.genres == ["folk rock"]


def test_leaked_names_are_scrubbed():
    leaky = {**GOOD, "vocal_delivery": "Dylan-esque nasal vocal like Bob", "genres": ["folk rock"]}

    def handler(request):
        return httpx.Response(200, json=_reply(leaky))

    traits = _translator(handler).translate("Bob Dylan")
    assert not mentions_reference(traits.model_dump_json(), "Bob Dylan")
    assert "nasal vocal" in traits.vocal_delivery


def test_scrub_keeps_band_stopwords_and_drops_empty_fields():
    t = StyleTraits(genres=["Beatles pop", "rock"], production="The Beatles")
    out = scrub(t, "The Beatles")
    assert out.genres == ["pop", "rock"] and out.production is None


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"error": {"message": "boom"}}),
        httpx.Response(200, json=_reply("not json")),
        httpx.Response(200, json=_reply({"genres": [], "instrumentation": []})),
    ],
)
def test_unusable_answers_raise(response):
    with pytest.raises(InspirationError):
        _translator(lambda request: response).translate("my cat")


def test_prompt_with_influences_never_contains_the_name():
    traits = FakeStyleTranslator().translate("Bob Dylan")
    p = compile_prompt(
        load_style("sunset-synthpop"), Intent(vocals=Vocals.VOCALS, influences=traits)
    )
    assert "Genre: folk rock (1960s), blended with synthpop" in p.text
    assert "harmonica" in p.text and "storytelling phrasing" in p.text
    assert "do not imitate any specific artist" in p.text
    assert not mentions_reference(p.text, "Bob Dylan")


def test_empty_reference_rejected():
    with pytest.raises(InspirationError):
        _translator(lambda r: httpx.Response(200)).translate("   ")


def test_artist_reference_drives_singer_tempo_production_and_instruments():
    """The station's voice ("soft, breathy") must not override the artist's (the bug where
    "like Bob Dylan" came out with a female voice)."""
    style = load_style("rainy-morning-indie")
    traits = FakeStyleTranslator().translate("Bob Dylan")
    p = compile_prompt(style, Intent(vocals=Vocals.VOCALS, influences=traits)).text
    lines = p.splitlines()
    assert lines[1].startswith("Genre: folk rock (1960s), blended with")
    assert "This is a song with a male lead singer and sung lyrics" in lines[2]
    assert (
        "Vocals: male lead singer; baritone, narrow range; nasal, reedy; half-spoken "
        "storytelling phrasing; loose pitch, no vibrato; weathered, wry; dry, close-miked; "
        "solo voice." in p
    )
    assert style.vocal_style not in p
    assert "Tempo: 95 BPM." in p  # the artist's typical tempo, not the station's
    assert "Production: raw, live-in-the-room." in p
    instruments = next(ln for ln in lines if ln.startswith("Instrumentation:"))
    assert instruments.index("harmonica") < instruments.index(style.instruments[0])
    assert "female vocals" in p.split("Avoid:")[1] and "polished studio pop" in p


def test_listener_singer_choice_beats_the_artist():
    traits = FakeStyleTranslator().translate("Bob Dylan")
    intent = Intent(vocals=Vocals.VOCALS, influences=traits, singer=Singer.FEMALE)
    p = compile_prompt(load_style("rainy-morning-indie"), intent).text
    assert "with a female lead singer" in p and "Avoid:" in p and "male vocals" in p
    assert "Vocals: female lead singer; nasal, reedy;" in p
    assert "baritone" not in p  # the artist's register doesn't fit the chosen voice


def test_singer_without_artist_and_instrumental_ignores_singer():
    style = load_style("rainy-morning-indie")
    p = compile_prompt(style, Intent(singer=Singer.MALE)).text
    assert f"Vocals: male lead singer; {style.vocal_style}." in p
    p = compile_prompt(style, Intent(singer=Singer.MALE, vocals=Vocals.INSTRUMENTAL)).text
    assert "male" not in p and "Instrumental only" in p


def test_voice_profile_is_parsed_scrubbed_and_era_requested():
    seen = {}
    leaky = {**GOOD, "voice": {**GOOD["voice"], "character": "young Dylan, wry"}}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_reply(leaky))

    traits = _translator(handler).translate("Bob Dylan 1965")
    schema = seen["body"]["response_format"]["schema"]
    assert {"voice", "era"} <= set(schema["required"])
    assert "names a period" in seen["body"]["system_instruction"]
    assert traits.voice.voice_type == "tenor, narrow range"
    assert traits.voice.character == "young, wry"  # the name was scrubbed
    assert traits.voice_text().startswith("tenor, narrow range; nasal, reedy; half-spoken")


def test_voice_without_profile_falls_back_to_delivery_phrase():
    t = StyleTraits(genres=["folk"], vocal_delivery="gravelly croon")
    assert t.voice_text() == "gravelly croon"


def test_listener_voice_tweaks_are_added_to_the_voice():
    traits = FakeStyleTranslator().translate("Bob Dylan")
    tweaks = VoiceTweaks(pitch=-1, grit=1, spoken=0, space=-1)
    intent = Intent(vocals=Vocals.VOCALS, influences=traits, voice_tweaks=tweaks)
    p = compile_prompt(load_style("rainy-morning-indie"), intent).text
    assert (
        "solo voice; sung low in the voice's range, rougher, grittier tone, "
        "dry, close and intimate." in p
    )
    assert VoiceTweaks().describe() == ""
