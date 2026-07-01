from __future__ import annotations
import asyncio
import contextlib
import json

from fastapi import WebSocket, WebSocketDisconnect

from app.agent.turn_intent.classifier import TurnIntentClassifier
from app.api.v1.llm import LLMService
from app.core.logging import get_logger
from app.stt.factory import get_stt_provider

log = get_logger(__name__)

END_OF_TURN_SILENCE = 1.0
IDLE_CONVERSATION_TIMEOUT = 45.0


class TranscriptionService:
    def __init__(self, websocket: WebSocket, user_email: str | None = None) -> None:
        self._ws = websocket
        self._provider = get_stt_provider()
        self._send_lock = asyncio.Lock()
        self._llm = LLMService(websocket, self._send_lock, user_email=user_email)
        self._turn_intent = TurnIntentClassifier()
        self._stream = None
        self._forward_task = None
        self._buffer: list[str] = []        
        self._silence_task = None
        self._answer_task = None
        self._idle_task = None
        self._finished_summary = False
        self._closing = False

    async def run(self) -> None:
        try:
            while True:
                message = await self._ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if self._closing:
                    break

                text = message.get("text")
                if text is not None:
                    await self._handle_control(text)
                    continue

                audio = message.get("bytes")
                if audio is not None:
                    if self._stream is None or self._forward_task.done():
                        await self._open_stream()
                    await self._stream.send_audio(audio)
        except WebSocketDisconnect:
            pass
        finally:
            await self._cleanup()

    async def _handle_control(self, text: str) -> None:
        if self._closing:
            return
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return
        if data.get("type") == "start":
            await self._llm.greet()   
        elif data.get("type") == "stop":
            await self._close_conversation("client_stop")

    async def _finish_summary(self) -> None:
        if self._finished_summary:
            return
        self._finished_summary = True
        await self._llm.finish()

    async def _open_stream(self) -> None:
        if self._stream is not None:
            await self._stream.close()
        self._stream = await self._provider.open_stream()
        self._forward_task = asyncio.create_task(self._forward_transcripts())
        log.info("transcription stream opened (provider=%s)", self._provider.name)

    async def _forward_transcripts(self) -> None:
        async for transcript in self._stream.transcripts():
            if self._closing:
                break
            self._cancel_idle_timer()
            async with self._send_lock:
                with contextlib.suppress(Exception):
                    await self._ws.send_json(
                        {
                            "type": "transcript",
                            "text": transcript.text,
                            "is_final": transcript.is_final,
                        }
                    )
            if transcript.is_final and transcript.text.strip():
                self._buffer.append(transcript.text)
            # any transcript means the caller is still talking — (re)start the silence
            # timer; it fires the answer only once they've actually stopped.
            self._restart_silence_timer()

    def _restart_silence_timer(self) -> None:
        if self._closing:
            return
        if self._silence_task is not None and not self._silence_task.done():
            self._silence_task.cancel()
        self._silence_task = asyncio.create_task(self._answer_when_silent())

    async def _answer_when_silent(self) -> None:
        try:
            await asyncio.sleep(END_OF_TURN_SILENCE)
        except asyncio.CancelledError:
            return
        if self._closing:
            return
        self._silence_task = None     # committed to answering; don't let a stray transcript cancel it
        question = " ".join(self._buffer).strip()
        self._buffer = []
        if question:
            log.info("end of turn -> llm: %r", question)
            if await self._is_end_conversation(question):
                await self._close_conversation("user_exit")
                return
            self._answer_task = asyncio.current_task()
            reply = await self._llm.answer(question)
            if self._should_arm_idle_close(reply):
                self._restart_idle_timer()

    def _restart_idle_timer(self) -> None:
        if self._closing:
            return
        self._cancel_idle_timer()
        self._idle_task = asyncio.create_task(self._close_when_idle())

    def _cancel_idle_timer(self) -> None:
        current = asyncio.current_task()
        if self._idle_task is not None and self._idle_task is not current and not self._idle_task.done():
            self._idle_task.cancel()

    async def _close_when_idle(self) -> None:
        try:
            await asyncio.sleep(IDLE_CONVERSATION_TIMEOUT)
        except asyncio.CancelledError:
            return
        await self._close_conversation("idle_timeout")

    async def _close_conversation(self, reason: str) -> None:
        if self._closing:
            return
        self._closing = True
        self._cancel_idle_timer()
        await self._llm.close_conversation(reason)
        self._finished_summary = True
        with contextlib.suppress(Exception):
            await self._ws.close(code=1000, reason=reason)

    async def _is_end_conversation(self, text: str) -> bool:
        if not self._may_be_end_conversation(text):
            return False
        result = await self._turn_intent.classify(self._llm.history, text)
        log.info(
            "turn intent classified: intent=%s confidence=%.2f reason=%s",
            result.intent,
            result.confidence,
            result.reason,
        )
        return result.should_end

    @staticmethod
    def _may_be_end_conversation(text: str) -> bool:
        lower = text.lower()
        return any(
            phrase in lower
            for phrase in (
                "bye",
                "goodbye",
                "thank",
                "thanks",
                "that's it",
                "that is it",
                "nothing else",
                "no more",
                "wrap up",
                "close",
                "end",
                "stop",
                "done",
                "fine for now",
                "all for now",
            )
        )

    @staticmethod
    def _should_arm_idle_close(reply: str | None) -> bool:
        if not reply:
            return False
        lower = reply.lower()
        return any(
            phrase in lower
            for phrase in (
                "anything else",
                "further assistance",
                "need any more",
                "if you need",
                "when we wrap up",
                "have a great day",
                "would you like their contact details",
            )
        )

    async def _cleanup(self) -> None:
        for task in (self._silence_task, self._answer_task, self._forward_task, self._idle_task):
            if task is not None:
                task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            if self._forward_task is not None:
                await self._forward_task
        if self._stream is not None:
            await self._stream.close()
        await self._finish_summary()
        log.info("transcription session ended")
