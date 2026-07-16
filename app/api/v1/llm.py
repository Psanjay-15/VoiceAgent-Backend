from __future__ import annotations
import asyncio
import contextlib
import re

from fastapi import WebSocket

from app.agent.business_actions import BusinessActionAgent
from app.api.v1.tts import TTSService
from app.core.logging import get_logger
from app.llm.factory import get_llm_provider

log = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a friendly voice assistant for an Indian real estate and home-renovation company. "
    "Help callers with buying, selling, renting, renovation, and appointments. Keep replies short "
    "and natural for a phone call, usually one or two sentences. Ask one useful follow-up at a time "
    "for missing details such as location, budget, BHK/property type, timeline, or renovation scope. "
    "Do not re-ask details already provided. For meeting or calendar requests, cooperate and use "
    "the system's saved invite email without asking the caller for an email. For unsupported document or "
    "contact-detail requests, say the team will follow up instead "
    "of promising to send files. Do not invent listings, exact prices, legal advice, or financial "
    "advice. If unsure, say a human expert from the team will follow up. Keep unrelated questions "
    "gently redirected to real estate or renovation."
)

_SPEAKABLE_PUNCTUATION = re.compile(r"[,;:!?]\s+|[.!?]\s*$")
_MIN_CHUNK_WORDS = 8
_MAX_CHUNK_CHARS = 80

GREETING = (
    "Hi! how can I help you?"
)

GOODBYE = (
    "Thanks for speaking with us. Our team will follow up if needed. Have a great day!"
)


class LLMService:
    """Streams the LLM reply, feeds it chunk-by-chunk to TTS, and keeps the
    running conversation so the model remembers what the caller already said."""

    def __init__(
        self,
        websocket: WebSocket,
        send_lock: asyncio.Lock,
        user_email: str | None = None,
    ) -> None:
        self._ws = websocket
        self._lock = send_lock
        self._provider = get_llm_provider()
        self._tts = TTSService(websocket, send_lock)
        self._actions = BusinessActionAgent(known_user_email=user_email)
        self._history: list[dict] = []   # running [user/assistant] turns for context
        self._finish_lock = asyncio.Lock()
        self._finished = False

    @property
    def history(self) -> list[dict]:
        return list(self._history)

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

    async def answer(self, question: str) -> str:
        action_response = await self._run_actions(question)
        if action_response:
            await self._send_spoken_reply(question, action_response)
            return action_response

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
        try:
            async for token in self._provider.stream_reply(messages):
                await self._send({"type": "llm", "text": token})
                reply += token
                buffer += token
                while True:
                    chunk, buffer = self._take_speakable_chunk(buffer)
                    if not chunk:
                        break
                    await tts_queue.put(chunk)

            if buffer.strip():
                await tts_queue.put(buffer.strip())
            await tts_queue.put(None)
            await tts_task
            await self._send({"type": "llm_end"})
        except asyncio.CancelledError:
            tts_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await tts_task
            await self._send({"type": "llm_interrupted"})
            raise

        self._history.append({"role": "user", "content": question})
        self._history.append({"role": "assistant", "content": reply})
        return reply

    async def finish(self) -> None:
        """Send the final admin summary and queued business actions when the call ends."""
        async with self._finish_lock:
            if self._finished:
                return
            self._finished = True
            try:
                await self._actions.flush_pending_actions(self._history)
            except Exception as e:
                log.warning("final action flush failed: %s", e)

    async def close_conversation(self, reason: str = "user_exit") -> None:
        """Speak a closing line and send the final admin summary."""
        log.info("closing conversation (reason=%s)", reason)
        if not self._last_assistant_reply_was_closing():
            await self._send_spoken_reply("", GOODBYE, remember_user=False)
        await self.finish()

    async def _run_actions(self, question: str) -> str | None:
        try:
            result = await self._actions.run(self._history, question)
        except Exception as e:
            log.warning("business action graph failed: %s", e)
            return None
        if result.status and result.status != "no_action":
            log.info("business action graph status=%s", result.status)
        return result.response

    async def _send_spoken_reply(self, question: str, reply: str, remember_user: bool = True) -> None:
        try:
            await self._send({"type": "llm_start"})
            await self._send({"type": "llm", "text": reply})
            await self._tts.speak(reply)
            await self._send({"type": "llm_end"})
        except asyncio.CancelledError:
            await self._send({"type": "llm_interrupted"})
            raise
        if remember_user and question:
            self._history.append({"role": "user", "content": question})
        self._history.append({"role": "assistant", "content": reply})

    def _last_assistant_reply_was_closing(self) -> bool:
        for item in reversed(self._history):
            if item["role"] != "assistant":
                continue
            lower = item["content"].lower()
            return any(
                phrase in lower
                for phrase in (
                    "have a great day",
                    "feel free to call",
                    "thanks for speaking",
                    "thank you",
                    "goodbye",
                    "bye",
                )
            )
        return False

    async def _tts_worker(self, queue: asyncio.Queue) -> None:
        while True:
            sentence = await queue.get()
            if sentence is None:
                break
            with contextlib.suppress(Exception):
                await self._tts.speak(sentence)

    @staticmethod
    def _take_speakable_chunk(buffer: str) -> tuple[str, str]:
        """Pull a short natural TTS chunk from the stream buffer."""
        stripped = buffer.strip()
        if not stripped:
            return "", buffer

        punctuation = _SPEAKABLE_PUNCTUATION.search(buffer)
        if punctuation:
            end = punctuation.end()
            return buffer[:end].strip(), buffer[end:]

        words = stripped.split()
        if len(words) >= _MIN_CHUNK_WORDS or len(stripped) >= _MAX_CHUNK_CHARS:
            split_at = _chunk_boundary(buffer)
            return buffer[:split_at].strip(), buffer[split_at:]

        return "", buffer


def _chunk_boundary(buffer: str) -> int:
    words_seen = 0
    for index, char in enumerate(buffer):
        if char.isspace():
            words_seen += 1
            if words_seen >= _MIN_CHUNK_WORDS:
                return index + 1
    return len(buffer)
