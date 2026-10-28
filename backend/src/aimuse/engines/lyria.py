"""Lyria via the Gemini Interactions REST API.

Docs: https://ai.google.dev/gemini-api/docs/music-generation
We call REST directly (httpx) rather than the SDK so the request/response shape is explicit
and easy to stub in tests.
"""

from __future__ import annotations

import base64
import time

import httpx

from ..models import AudioAsset, EnginePrompt
from .base import EngineError

API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

# Paid tier, per request (Gemini API pricing page, 2026-10-28). Used for budget caps.
LYRIA_PRICES_USD = {
    "lyria-3.5": 0.08,
    "lyria-3-pro-preview": 0.08,
    "lyria-3-clip-preview": 0.04,
}

_FORMATS = {"mp3": "audio/mp3", "wav": "audio/wav"}
# Only retry when the server clearly did no work (rate limit / overloaded), so a retry can't
# double-bill a generation that actually ran.
_RETRY_STATUS = {429, 503}


class LyriaEngine:
    id = "lyria"

    def __init__(
        self,
        api_key: str,
        model: str = "lyria-3.5",
        output_format: str = "mp3",
        *,
        client: httpx.Client | None = None,
        timeout_s: float = 300.0,
        max_retries: int = 2,
        retry_wait_s: float = 5.0,
    ) -> None:
        if not api_key:
            raise ValueError("a Gemini API key is required (set GEMINI_API_KEY)")
        if model not in LYRIA_PRICES_USD:
            raise ValueError(f"unknown Lyria model {model!r}; known: {sorted(LYRIA_PRICES_USD)}")
        if output_format not in _FORMATS:
            raise ValueError(f"output_format must be one of {sorted(_FORMATS)}")
        if output_format == "wav" and model != "lyria-3.5":
            raise ValueError("WAV output is only supported by lyria-3.5")
        self.model = model
        self.output_format = output_format
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=timeout_s)
        self._max_retries = max_retries
        self._retry_wait_s = retry_wait_s

    @property
    def price_per_request_usd(self) -> float:
        return LYRIA_PRICES_USD[self.model]

    def build_body(self, prompt: EnginePrompt) -> dict:
        if prompt.images:
            content: str | list[dict] = [{"type": "text", "text": prompt.text}] + [
                {
                    "type": "image",
                    "mime_type": img.mime_type,
                    "data": base64.b64encode(img.data).decode(),
                }
                for img in prompt.images[:10]
            ]
        else:
            content = prompt.text
        body: dict = {"model": self.model, "input": content}
        if self.output_format == "wav":
            body["response_format"] = {"type": "audio", "mime_type": _FORMATS["wav"]}
        return body

    def _post(self, body: dict) -> dict:
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.post(API_URL, json=body, headers=headers)
            except httpx.TransportError as e:
                if isinstance(e, httpx.ConnectError) and attempt < self._max_retries:
                    time.sleep(self._retry_wait_s * (2**attempt))
                    continue
                raise EngineError(f"network error calling Lyria: {e}") from e
            if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                time.sleep(self._retry_wait_s * (2**attempt))
                continue
            if resp.status_code >= 400:
                raise EngineError(f"Lyria API error {resp.status_code}: {_error_message(resp)}")
            return resp.json()
        raise AssertionError("unreachable")

    def generate(self, prompt: EnginePrompt) -> AudioAsset:
        data = self._post(self.build_body(prompt))
        audio_b64, mime, texts = None, None, []
        for step in data.get("steps", []):
            if step.get("type") != "model_output":
                continue
            for block in step.get("content", []):
                if block.get("type") == "audio" and block.get("data"):
                    audio_b64 = block["data"]
                    mime = block.get("mime_type")
                elif block.get("type") == "text" and block.get("text"):
                    texts.append(block["text"])
        if not audio_b64:
            detail = " ".join(texts)[:300] or data.get("status") or "no audio in response"
            raise EngineError(f"Lyria returned no audio: {detail}")
        return AudioAsset(
            data=base64.b64decode(audio_b64),
            mime_type=mime or _FORMATS[self.output_format],
            lyrics="\n".join(texts) or None,
            engine=self.id,
            model=self.model,
            cost_usd=self.price_per_request_usd,
        )


def _error_message(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error", {})
        return str(err.get("message") or err)[:500]
    except ValueError:
        return resp.text[:500]
