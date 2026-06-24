from __future__ import annotations
from functools import lru_cache

from app.config import settings
from app.core.exceptions import UnsupportedProviderError
from app.llm.base import LLMProvider
from app.llm.gemini import GeminiLLM
from app.llm.openai import OpenAILLM

PROVIDERS: dict[str, type[LLMProvider]] = {
    "gemini": GeminiLLM,
    "openai": OpenAILLM,
}


@lru_cache(maxsize=4)
def get_llm_provider(name: str | None = None) -> LLMProvider:
    """Return the configured LLM provider (defaults to LLM_PROVIDER from env)."""
    provider = (name or settings.llm_provider).lower()
    if provider not in PROVIDERS:
        raise UnsupportedProviderError(
            f"Unknown LLM provider '{provider}'. Available: {sorted(PROVIDERS)}"
        )
    return PROVIDERS[provider]()
