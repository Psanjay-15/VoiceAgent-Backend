from __future__ import annotations
from collections.abc import AsyncIterator

from app.config import settings
from app.core.exceptions import TTSError
from app.tts.base import TTSProvider


class ElevenLabsTTS(TTSProvider):
    name = "elevenlabs"

    def __init__(self) -> None:
        if not settings.elevenlabs_api_key:
            raise TTSError("ELEVENLABS_API_KEY is not set")
        self._api_key = settings.elevenlabs_api_key

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        raise NotImplementedError("ElevenLabs TTS is implemented later")
        yield b""  
