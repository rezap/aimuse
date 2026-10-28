import base64
import json

import httpx
import pytest

from aimuse.engines import EngineError, LyriaEngine
from aimuse.models import Intent
from aimuse.prompt import compile_prompt


def _ok_response(audio=b"ID3fake", mime="audio/mp3"):
    return {
        "steps": [
            {"type": "user_input"},
            {
                "type": "model_output",
                "content": [
                    {"type": "text", "text": "[Verse]\nla la"},
                    {"type": "audio", "mime_type": mime, "data": base64.b64encode(audio).decode()},
                ],
            },
        ]
    }


def _engine(handler, **kw):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return LyriaEngine("test-key", client=client, retry_wait_s=0, **kw)


def test_generate_parses_audio_and_lyrics(style):
    seen = {}

    def handler(request: httpx.Request):
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_response())

    asset = _engine(handler).generate(compile_prompt(style, Intent(theme="x")))
    assert asset.data == b"ID3fake" and asset.mime_type == "audio/mp3"
    assert asset.lyrics == "[Verse]\nla la"
    assert asset.cost_usd == 0.08 and asset.model == "lyria-3.5"
    assert seen["headers"]["x-goog-api-key"] == "test-key"
    assert seen["body"]["model"] == "lyria-3.5"
    assert isinstance(seen["body"]["input"], str)
    assert "response_format" not in seen["body"]


def test_body_with_image_and_wav(style):
    eng = _engine(lambda r: httpx.Response(200, json=_ok_response()), output_format="wav")
    body = eng.build_body(compile_prompt(style, Intent(), use_anchor_image=True))
    assert body["response_format"] == {"type": "audio", "mime_type": "audio/wav"}
    assert body["input"][0]["type"] == "text"
    assert body["input"][1]["type"] == "image" and body["input"][1]["mime_type"] == "image/png"
    base64.b64decode(body["input"][1]["data"])


def test_retries_rate_limit_then_succeeds(style):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json=_ok_response())

    _engine(handler).generate(compile_prompt(style, Intent()))
    assert len(calls) == 2


def test_server_error_is_not_retried(style):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={"error": {"message": "boom"}})

    with pytest.raises(EngineError, match="500: boom"):
        _engine(handler).generate(compile_prompt(style, Intent()))
    assert len(calls) == 1


def test_no_audio_raises(style):
    def handler(request):
        content = [{"type": "text", "text": "blocked"}]
        body = {"steps": [{"type": "model_output", "content": content}]}
        return httpx.Response(200, json=body)

    with pytest.raises(EngineError, match="blocked"):
        _engine(handler).generate(compile_prompt(style, Intent()))


def test_config_validation():
    with pytest.raises(ValueError):
        LyriaEngine("")
    with pytest.raises(ValueError):
        LyriaEngine("k", model="lyria-99")
    with pytest.raises(ValueError):
        LyriaEngine("k", model="lyria-3-clip-preview", output_format="wav")
    assert LyriaEngine("k", model="lyria-3-clip-preview").price_per_request_usd == 0.04
