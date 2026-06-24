from __future__ import annotations
from functools import lru_cache

from app.config import settings
from app.core.exceptions import UnsupportedProviderError
from app.tts.base import TTSProvider
from app.tts.deepgram import DeepgramTTS
from app.tts.elevenlabs import ElevenLabsTTS
from app.tts.openai import OpenAITTS

PROVIDERS: dict[str, type[TTSProvider]] = {
    "deepgram": DeepgramTTS,
    "openai": OpenAITTS,
    "elevenlabs": ElevenLabsTTS,
}


@lru_cache(maxsize=4)
def get_tts_provider(name: str | None = None) -> TTSProvider:
    """Return the configured TTS provider (defaults to TTS_PROVIDER from env)."""
    provider = (name or settings.tts_provider).lower()
    if provider not in PROVIDERS:
        raise UnsupportedProviderError(
            f"Unknown TTS provider '{provider}'. Available: {sorted(PROVIDERS)}"
        )
    return PROVIDERS[provider]()
