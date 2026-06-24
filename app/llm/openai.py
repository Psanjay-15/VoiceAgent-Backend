from __future__ import annotations
from collections.abc import AsyncIterator

from app.config import settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.llm.base import LLMProvider, Message

log = get_logger(__name__)


class OpenAILLM(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY is not set")
        self._api_key = settings.openai_api_key
        self._model = settings.openai_model or "gpt-4o-mini"

    async def stream_reply(self, messages: list[Message]) -> AsyncIterator[str]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key)
        stream = await client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
