from __future__ import annotations
import asyncio
import contextlib
import json
from fastapi import WebSocket, WebSocketDisconnect
from app.api.v1.llm import LLMService
from app.core.logging import get_logger
from app.stt.factory import get_stt_provider

log = get_logger(__name__)


class TranscriptionService:
    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._provider = get_stt_provider()
        self._send_lock = asyncio.Lock()
        self._llm = LLMService(websocket, self._send_lock)
        self._stream = None
        self._forward_task = None
        self._buffer: list[str] = []        # final transcripts collected for this turn

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
        if data.get("type") == "stop":
            await self._end_turn()

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

    async def _end_turn(self) -> None:
        """User pressed stop: flush the STT stream, gather the full transcript, answer."""
        if self._stream is not None:
            await self._stream.close()         
        if self._forward_task is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._forward_task        
        question = " ".join(self._buffer).strip()
        self._buffer = []
        self._stream = None
        self._forward_task = None
        if question:
            log.info("end of turn -> llm: %r", question)
            await self._llm.answer(question)

    async def _cleanup(self) -> None:
        if self._forward_task is not None:
            self._forward_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._forward_task
        if self._stream is not None:
            await self._stream.close()
        log.info("transcription session ended")
