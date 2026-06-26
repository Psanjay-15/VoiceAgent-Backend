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
    "You are a friendly, knowledgeable voice assistant for an Indian real estate and "
    "home-renovation company. You help callers buy, sell, or rent homes and plan home "
    "renovation or interior work anywhere in India. "
    "Use Indian real estate context naturally — BHK layouts, carpet vs built-up area, "
    "prices in lakhs and crores, localities and societies, RERA, home loans, possession "
    "timelines, and typical renovation work. "
    "This is a spoken phone call, so keep replies short and natural (one or two "
    "sentences), and when useful ask ONE brief follow-up to understand their need: "
    "whether they want to buy, sell, rent, or renovate, plus property type, location, "
    "budget, and timeline. Do not re-ask anything the caller has already told you if you are clear. "
    "Never invent specific listings, exact prices, or legal/financial advice — if "
    "unsure, say a human expert from the team will follow up. Keep the conversation on "
    "real estate and renovation; gently steer back if asked about something unrelated."
    "\n\nHere are examples of how you should respond:\n\n"
    "Caller: I'm looking for a 3 BHK in Bangalore.\n"
    "You: Great! Which area of Bangalore are you considering, and what's your budget range?\n\n"
    "Caller: I want to renovate my bathroom.\n"
    "You: Sure! Is it a full remodel or mainly new fixtures and tiling, and roughly what size is it?\n\n"
    "Caller: I need a 1 BHK on rent in Pune.\n"
    "You: Got it. Which locality in Pune works for you, and what monthly rent are you targeting?\n\n"
    "Caller: I want to sell my flat in Mumbai.\n"
    "You: Happy to help. Which area is the flat in, and what price are you expecting?\n\n"
    "Caller: Tell me a joke.\n"
    "You: I'm here for real estate and home renovation — are you looking to buy, rent, or renovate a home?"
)

_SENTENCE_END = re.compile(r"[.!?]")

GREETING = (
    "Hi! how can I help you?"
)


class LLMService:
    """Streams the LLM reply, feeds it sentence-by-sentence to TTS, and keeps the
    running conversation so the model remembers what the caller already said."""

    def __init__(self, websocket: WebSocket, send_lock: asyncio.Lock) -> None:
        self._ws = websocket
        self._lock = send_lock
        self._provider = get_llm_provider()
        self._tts = TTSService(websocket, send_lock)
        self._history: list[dict] = []   # running [user/assistant] turns for context

    async def _send(self, payload: dict) -> None:
        async with self._lock:
            with contextlib.suppress(Exception):
                await self._ws.send_json(payload)

    async def greet(self) -> None:
        """Agent speaks first — send the greeting text and synthesize it."""
        await self._send({"type": "llm_start"})
        await self._send({"type": "llm", "text": GREETING})
        await self._tts.speak(GREETING)
        await self._send({"type": "llm_end"})
        self._history.append({"role": "assistant", "content": GREETING})

    async def answer(self, question: str) -> None:
        messages = (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + self._history
            + [{"role": "user", "content": question}]
        )
        log.info("llm answering (provider=%s): %r", self._provider.name, question)
        await self._send({"type": "llm_start"})

        tts_queue: asyncio.Queue = asyncio.Queue()
        tts_task = asyncio.create_task(self._tts_worker(tts_queue))

        reply = ""
        buffer = ""
        async for token in self._provider.stream_reply(messages):
            await self._send({"type": "llm", "text": token})
            reply += token
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

        self._history.append({"role": "user", "content": question})
        self._history.append({"role": "assistant", "content": reply})

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
