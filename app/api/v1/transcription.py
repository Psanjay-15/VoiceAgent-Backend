from __future__ import annotations
import asyncio
import contextlib
from fastapi import WebSocket, WebSocketDisconnect
from app.core.logging import get_logger
from app.stt.factory import get_stt_provider

log = get_logger(__name__)

class TranscriptionService:
    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._provider = get_stt_provider()
        self._stream = None
        self._forward_task = None

    async def run(self) -> None:
        try:
            while True:
                message = await self._ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                audio = message.get("bytes")
                if audio is None:
                    continue
                if self._stream is None or self._forward_task.done():
                    await self._open_stream()
                await self._stream.send_audio(audio)
        except WebSocketDisconnect:
            pass
        finally:
            await self._cleanup()

    async def _open_stream(self) -> None:
        if self._stream is not None:
            await self._stream.close()
        self._stream = await self._provider.open_stream()
        self._forward_task = asyncio.create_task(self._forward_transcripts())
        log.info("transcription stream opened (provider=%s)", self._provider.name)

    async def _forward_transcripts(self) -> None:
        async for transcript in self._stream.transcripts():
            await self._ws.send_json(
                {
                    "type": "transcript",
                    "text": transcript.text,
                    "is_final": transcript.is_final,
                }
            )

    async def _cleanup(self) -> None:
        if self._forward_task is not None:
            self._forward_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._forward_task
        if self._stream is not None:
            await self._stream.close()
        log.info("transcription session ended")
