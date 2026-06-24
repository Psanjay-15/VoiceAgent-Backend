from __future__ import annotations
from collections.abc import AsyncIterator

from app.config import settings
from app.core.exceptions import TTSError
from app.tts.base import TTSProvider


class OpenAITTS(TTSProvider):
    name = "openai"

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise TTSError("OPENAI_API_KEY is not set")
        self._api_key = settings.openai_api_key

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        raise NotImplementedError("OpenAI TTS is implemented later")
        yield b""  
