from __future__ import annotations
import asyncio
import contextlib
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
        self._runner = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            async with self._client.listen.v1.connect(**self._connect_kwargs) as connection:
                self._connection = connection
                connection.on(EventType.MESSAGE, self._on_message)
                connection.on(EventType.ERROR, lambda e: log.warning("deepgram error: %s", e))
                connection.on(EventType.CLOSE, lambda _: self._queue.put_nowait(None))
                self._ready.set()
                await connection.start_listening()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("deepgram stream ended: %s", e)
        finally:
            self._ready.set()
            self._queue.put_nowait(None)

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
        try:
            await self._connection.send_media(chunk)
        except Exception as e:
            log.warning("deepgram send_media failed: %s", e)

    async def transcripts(self):
        while True:
            item = await self._queue.get()
            if item is None:
                break
            yield item

    async def close(self) -> None:
        if self._connection is not None:
            with contextlib.suppress(Exception):
                await self._connection.send_close_stream()
        self._runner.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._runner


class DeepgramSTT(STTProvider):
    name = "deepgram"

    def __init__(self) -> None:
        if not settings.deepgram_api_key:
            raise STTError("DEEPGRAM_API_KEY is not set")
        self._api_key = settings.deepgram_api_key

    async def open_stream(
        self,
        *,
        sample_rate: int = 16000,
        encoding: str = "linear16",
        language: str = "en",
    ) -> STTStream:
        client = AsyncDeepgramClient(api_key=self._api_key)

        connect_kwargs = dict(
            model="nova-3",
            language=language,
            interim_results="true",  
            smart_format="true",    
        )
        return DeepgramSTTStream(client, connect_kwargs)
