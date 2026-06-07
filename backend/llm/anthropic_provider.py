"""
Anthropic Claude Provider
"""

import os
from typing import AsyncIterator

import anthropic

from .base import BaseLLMProvider, LLMConfig, LLMResponse, Message, ProviderName


class AnthropicProvider(BaseLLMProvider):
    name = ProviderName.ANTHROPIC
    default_model = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model or self.default_model
        self.client = anthropic.AsyncAnthropic(api_key=self.api_key)

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        cfg = config or LLMConfig()

        kwargs: dict = {
            "model": self.model,
            "max_tokens": cfg.max_tokens,
            "temperature": cfg.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            kwargs["system"] = system

        response = await self.client.messages.create(**kwargs)

        return LLMResponse(
            content=response.content[0].text,
            provider=self.name,
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            finish_reason=response.stop_reason or "stop",
        )

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        cfg = config or LLMConfig()
        kwargs: dict = {
            "model": self.model,
            "max_tokens": cfg.max_tokens,
            "temperature": cfg.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            kwargs["system"] = system

        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Anthropic doesn't have a native embed API; fall back to a simple hash-based mock
        # In production, use a dedicated embedding model
        raise NotImplementedError(
            "Anthropic does not provide embeddings. Use OpenAI or a local model."
        )
