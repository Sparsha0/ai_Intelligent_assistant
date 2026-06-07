"""
OpenAI Provider (also used for embeddings as fallback)
"""

import os
from typing import AsyncIterator

import openai

from .base import BaseLLMProvider, LLMConfig, LLMResponse, Message, ProviderName

EMBEDDING_MODEL = "text-embedding-3-small"


class OpenAIProvider(BaseLLMProvider):
    name = ProviderName.OPENAI
    default_model = "gpt-4o"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or self.default_model
        self.client = openai.AsyncOpenAI(api_key=self.api_key)

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        cfg = config or LLMConfig()

        formatted = []
        if system:
            formatted.append({"role": "system", "content": system})
        formatted += [{"role": m.role, "content": m.content} for m in messages]

        kwargs: dict = {
            "model": self.model,
            "messages": formatted,
            "max_tokens": cfg.max_tokens,
            "temperature": cfg.temperature,
        }
        if cfg.response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        return LLMResponse(
            content=choice.message.content or "",
            provider=self.name,
            model=self.model,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            finish_reason=choice.finish_reason or "stop",
        )

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        cfg = config or LLMConfig()
        formatted = []
        if system:
            formatted.append({"role": "system", "content": system})
        formatted += [{"role": m.role, "content": m.content} for m in messages]

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=formatted,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
        )
        return [item.embedding for item in response.data]
