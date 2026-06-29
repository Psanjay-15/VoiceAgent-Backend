from __future__ import annotations

from app.llm.base import LLMProvider, Message


async def collect_reply(provider: LLMProvider, messages: list[Message]) -> str:
    chunks = []
    async for token in provider.stream_reply(messages):
        chunks.append(token)
    return "".join(chunks)
