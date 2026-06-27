from __future__ import annotations
import asyncio
import contextlib
import time
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from app.config import settings
from app.core.exceptions import STTError
from app.core.logging import get_logger
from app.stt.base import STTProvider, STTStream, Transcript

log = get_logger(__name__)


class DeepgramSTTStream(STTStream):

    def __init__(self, client: AsyncDeepgramClient, connect_kwargs: dict) -> None:
        self._client = client
        self._connect_kwargs = connect_kwargs
        self._queue: asyncio.Queue = asyncio.Queue()
        self._connection = None
        self._ready = asyncio.Event()
        self._last_audio_at = time.monotonic()
        self._keepalive_task = None
        self._runner = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            async with self._client.listen.v1.connect(**self._connect_kwargs) as connection:
                self._connection = connection
                connection.on(EventType.MESSAGE, self._on_message)
                connection.on(EventType.ERROR, self._on_error)
                connection.on(EventType.CLOSE, lambda _: self._queue.put_nowait(None))
                self._ready.set()
                self._keepalive_task = asyncio.create_task(self._keepalive())
                await connection.start_listening()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            message = str(e)
            if "NET-0001" in message or "timeout window" in message:
                log.info("deepgram stream idle-timeout; it will reopen on next audio")
            else:
                log.warning("deepgram stream ended: %s", e)
        finally:
            if self._keepalive_task is not None:
                self._keepalive_task.cancel()
            self._ready.set()
            self._queue.put_nowait(None)

    def _on_error(self, error) -> None:
        message = str(error)
        if "NET-0001" in message or "timeout window" in message:
            log.info("deepgram stream idle-timeout; it will reopen on next audio")
            return
        log.warning("deepgram error: %s", error)

    def _on_message(self, result) -> None:
        if getattr(result, "type", None) != "Results":
            return
        try:
            transcript = result.channel.alternatives[0].transcript
        except (AttributeError, IndexError):
            return
        if transcript:
            self._queue.put_nowait(Transcript(text=transcript, is_final=bool(result.is_final)))

    async def send_audio(self, chunk: bytes) -> None:
        await self._ready.wait()
        if self._connection is None:
            return
        self._last_audio_at = time.monotonic()
        try:
            await self._connection.send_media(chunk)
        except Exception as e:
            log.warning("deepgram send_media failed: %s", e)

    async def _keepalive(self) -> None:
        while True:
            await asyncio.sleep(5)
            if self._connection is None:
                continue
            if time.monotonic() - self._last_audio_at < 5:
                continue
            for method_name in ("send_keep_alive", "keep_alive"):
                method = getattr(self._connection, method_name, None)
                if method is None:
                    continue
                with contextlib.suppress(Exception):
                    result = method()
                    if asyncio.iscoroutine(result):
                        await result
                break

    async def transcripts(self):
        while True:
            item = await self._queue.get()
            if item is None:
                break
            yield item

    async def close(self) -> None:
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
        if self._connection is not None:
            with contextlib.suppress(Exception):
                await self._connection.send_close_stream()
        with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError, Exception):
            await asyncio.wait_for(self._runner, timeout=2.0)
        if not self._runner.done():
            self._runner.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._runner


class DeepgramSTT(STTProvider):
    name = "deepgram"

    def __init__(self) -> None:
        if not settings.deepgram_api_key:
            raise STTError("DEEPGRAM_API_KEY is not set")
        self._api_key = settings.deepgram_api_key
        self._model = settings.deepgram_stt_model

    async def open_stream(
        self,
        *,
        sample_rate: int = 16000,
        encoding: str = "linear16",
        language: str = "en",
    ) -> STTStream:
        client = AsyncDeepgramClient(api_key=self._api_key)

        connect_kwargs = dict(
            model=self._model,
            language=language,
            interim_results="true",  
            smart_format="true",    
        )
        return DeepgramSTTStream(client, connect_kwargs)
