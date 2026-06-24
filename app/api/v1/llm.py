from __future__ import annotations
import asyncio
import contextlib
import re

from fastapi import WebSocket

from app.api.v1.tts import TTSService
from app.core.logging import get_logger
from app.llm.factory import get_llm_provider

log = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a helpful voice assistant. Reply briefly and conversationally, "
    "in one or two short sentences, as if speaking out loud."
)

_SENTENCE_END = re.compile(r"[.!?]")


class LLMService:
    """Streams the LLM reply as text, and feeds it sentence-by-sentence to TTS."""

    def __init__(self, websocket: WebSocket, send_lock: asyncio.Lock) -> None:
        self._ws = websocket
        self._lock = send_lock
        self._provider = get_llm_provider()
        self._tts = TTSService(websocket, send_lock)

    async def _send(self, payload: dict) -> None:
        async with self._lock:
            with contextlib.suppress(Exception):
                await self._ws.send_json(payload)

    async def answer(self, question: str) -> None:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        log.info("llm answering (provider=%s): %r", self._provider.name, question)
        await self._send({"type": "llm_start"})

        tts_queue: asyncio.Queue = asyncio.Queue()
        tts_task = asyncio.create_task(self._tts_worker(tts_queue))

        buffer = ""
        async for token in self._provider.stream_reply(messages):
            await self._send({"type": "llm", "text": token})
            buffer += token
            while True:
                sentence, buffer = self._take_sentence(buffer)
                if not sentence:
                    break
                await tts_queue.put(sentence)

        if buffer.strip():
            await tts_queue.put(buffer.strip())
        await tts_queue.put(None)     
        await tts_task               
        await self._send({"type": "llm_end"})

    async def _tts_worker(self, queue: asyncio.Queue) -> None:
        while True:
            sentence = await queue.get()
            if sentence is None:
                break
            with contextlib.suppress(Exception):
                await self._tts.speak(sentence)

    @staticmethod
    def _take_sentence(buffer: str) -> tuple[str, str]:
        """Pull the first complete sentence off the buffer; return (sentence, remainder)."""
        match = _SENTENCE_END.search(buffer)
        if not match:
            return "", buffer
        end = match.end()
        return buffer[:end].strip(), buffer[end:]
