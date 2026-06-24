from __future__ import annotations
import asyncio
import contextlib

from fastapi import WebSocket

from app.core.logging import get_logger
from app.tts.factory import get_tts_provider

log = get_logger(__name__)


class TTSService:

    def __init__(self, websocket: WebSocket, send_lock: asyncio.Lock) -> None:
        self._ws = websocket
        self._lock = send_lock
        self._provider = get_tts_provider()

    async def speak(self, text: str) -> None:
        # forward each audio chunk the moment it arrives (Deepgram streams raw PCM),
        # so playback can start without waiting for the whole sentence to synthesize.
        async for chunk in self._provider.synthesize(text):
            if not chunk:
                continue
            async with self._lock:
                with contextlib.suppress(Exception):
                    await self._ws.send_bytes(chunk)
