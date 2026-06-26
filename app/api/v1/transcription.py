from __future__ import annotations
import asyncio
import contextlib
import json

from fastapi import WebSocket, WebSocketDisconnect

from app.api.v1.llm import LLMService
from app.core.logging import get_logger
from app.stt.factory import get_stt_provider

log = get_logger(__name__)

END_OF_TURN_SILENCE = 1.5  


class TranscriptionService:
    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._provider = get_stt_provider()
        self._send_lock = asyncio.Lock()
        self._llm = LLMService(websocket, self._send_lock)
        self._stream = None
        self._forward_task = None
        self._buffer: list[str] = []        
        self._silence_task = None
        self._answer_task = None

    async def run(self) -> None:
        try:
            while True:
                message = await self._ws.receive()
                if message.get("type") == "websocket.disconnect":
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
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return
        if data.get("type") == "start":
            await self._llm.greet()   

    async def _open_stream(self) -> None:
        if self._stream is not None:
            await self._stream.close()
        self._stream = await self._provider.open_stream()
        self._forward_task = asyncio.create_task(self._forward_transcripts())
        log.info("transcription stream opened (provider=%s)", self._provider.name)

    async def _forward_transcripts(self) -> None:
        async for transcript in self._stream.transcripts():
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
        if self._silence_task is not None and not self._silence_task.done():
            self._silence_task.cancel()
        self._silence_task = asyncio.create_task(self._answer_when_silent())

    async def _answer_when_silent(self) -> None:
        try:
            await asyncio.sleep(END_OF_TURN_SILENCE)
        except asyncio.CancelledError:
            return
        self._silence_task = None     # committed to answering; don't let a stray transcript cancel it
        question = " ".join(self._buffer).strip()
        self._buffer = []
        if question:
            log.info("end of turn -> llm: %r", question)
            self._answer_task = asyncio.current_task()
            await self._llm.answer(question)

    async def _cleanup(self) -> None:
        for task in (self._silence_task, self._answer_task, self._forward_task):
            if task is not None:
                task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            if self._forward_task is not None:
                await self._forward_task
        if self._stream is not None:
            await self._stream.close()
        log.info("transcription session ended")
