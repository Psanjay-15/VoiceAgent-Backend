from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class TTSProvider(ABC):
    """Base class implemented by every TTS provider (deepgram, elevenlabs, ...)."""

    name: str = ""

    @abstractmethod
    def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Stream synthesized audio (bytes) for the given text."""
