from __future__ import annotations

from app.config import settings
from app.core.exceptions import STTError
from app.stt.base import STTProvider, STTStream


class OpenAISTT(STTProvider):
    name = "openai"

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise STTError("OPENAI_API_KEY is not set")
        self._api_key = settings.openai_api_key

    async def open_stream(
        self,
        *,
        sample_rate: int = 16000,
        encoding: str = "linear16",
        language: str = "en",
    ) -> STTStream:
        raise NotImplementedError("OpenAI STT is implemented later")
