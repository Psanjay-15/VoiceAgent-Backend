from __future__ import annotations
from collections.abc import AsyncIterator

from app.config import settings
from app.core.exceptions import TTSError
from app.core.logging import get_logger
from app.tts.base import TTSProvider

log = get_logger(__name__)

_SPEAK_URL = "https://api.deepgram.com/v1/speak"


class DeepgramTTS(TTSProvider):
    name = "deepgram"

    def __init__(self) -> None:
        if not settings.deepgram_api_key:
            raise TTSError("DEEPGRAM_API_KEY is not set")
        self._api_key = settings.deepgram_api_key
        self._model = settings.deepgram_tts_model

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        import httpx

        params = {
            "model": self._model,
            "encoding": "linear16",
            "container": "none",
            "sample_rate": "24000",
        }
        headers = {"Authorization": f"Token {self._api_key}"}
        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream(
                "POST", _SPEAK_URL, params=params, headers=headers, json={"text": text}
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise TTSError(f"Deepgram TTS failed: {resp.status_code} {body[:200]!r}")
                async for chunk in resp.aiter_bytes():
                    yield chunk
