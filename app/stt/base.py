from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class Transcript:
    text: str
    is_final: bool


class STTStream(ABC):

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None:
        """Send one chunk of audio to the provider."""

    @abstractmethod
    def transcripts(self) -> AsyncIterator[Transcript]:
        """Async-iterate transcripts (interim + final) as they arrive."""

    @abstractmethod
    async def close(self) -> None:
        """Close the session and release the connection."""


class STTProvider(ABC):

    name: str = ""

    @abstractmethod
    async def open_stream(
        self,
        *,
        sample_rate: int = 16000,
        encoding: str = "linear16",
        language: str = "en",
    ) -> STTStream:
        """Open a new streaming-transcription session."""
