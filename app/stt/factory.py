from __future__ import annotations
from functools import lru_cache
from app.config import settings
from app.core.exceptions import UnsupportedProviderError
from app.stt.base import STTProvider
from app.stt.deepgram import DeepgramSTT
from app.stt.elevenlabs import ElevenLabsSTT
from app.stt.openai import OpenAISTT

PROVIDERS: dict[str, type[STTProvider]] = {
    "deepgram": DeepgramSTT,
    "openai": OpenAISTT,
    "elevenlabs": ElevenLabsSTT,
}


@lru_cache(maxsize=4)
def get_stt_provider(name: str | None = None) -> STTProvider:
    provider = (name or settings.stt_provider).lower()
    if provider not in PROVIDERS:
        raise UnsupportedProviderError(
            f"Unknown STT provider '{provider}'. Available: {sorted(PROVIDERS)}"
        )
    return PROVIDERS[provider]()
