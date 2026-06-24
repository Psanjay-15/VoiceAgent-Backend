from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

Message = dict[str, str] 


class LLMProvider(ABC):
    """Base class implemented by every LLM provider (gemini, openai, ...)."""

    name: str = ""

    @abstractmethod
    def stream_reply(self, messages: list[Message]) -> AsyncIterator[str]:
        """Stream the assistant's reply token-by-token for the given messages."""
