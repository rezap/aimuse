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
from aimuse.models import Intent, StyleTraits, Vocals
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
    assert traits.summary() == "folk rock · early 1960s · acoustic guitar, harmonica"


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
    assert "Style influences: folk rock (1960s)" in p.text
    assert "harmonica" in p.text and "storytelling vocal" in p.text
    assert "do not imitate any specific artist" in p.text
    assert not mentions_reference(p.text, "Bob Dylan")


def test_empty_reference_rejected():
    with pytest.raises(InspirationError):
        _translator(lambda r: httpx.Response(200)).translate("   ")
