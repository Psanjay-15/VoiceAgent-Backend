from __future__ import annotations
from collections.abc import AsyncIterator

from app.config import settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.llm.base import LLMProvider, Message

log = get_logger(__name__)


class GeminiLLM(LLMProvider):
    name = "gemini"

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        self._api_key = settings.gemini_api_key
        self._model = settings.gemini_model
        self._client = None

    async def stream_reply(self, messages: list[Message]) -> AsyncIterator[str]:
        from google import genai
        from google.genai import types

        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)

        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        contents = [
            types.Content(
                role="model" if m["role"] == "assistant" else "user",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages
            if m["role"] != "system"
        ]
        config = types.GenerateContentConfig(
            system_instruction=system,
            thinking_config=types.ThinkingConfig(thinking_budget=0),  
        )

        stream = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=config,
        )
        async for chunk in stream:
            if chunk.text:
                yield chunk.text
