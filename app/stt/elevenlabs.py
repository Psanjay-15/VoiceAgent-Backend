from __future__ import annotations

from app.config import settings
from app.core.exceptions import STTError
from app.stt.base import STTProvider, STTStream


class ElevenLabsSTT(STTProvider):
    name = "elevenlabs"

    def __init__(self) -> None:
        if not settings.elevenlabs_api_key:
            raise STTError("ELEVENLABS_API_KEY is not set")
        self._api_key = settings.elevenlabs_api_key

    async def open_stream(
        self,
        *,
        sample_rate: int = 16000,
        encoding: str = "linear16",
        language: str = "en",
    ) -> STTStream:
        raise NotImplementedError("ElevenLabs STT is implemented later")
