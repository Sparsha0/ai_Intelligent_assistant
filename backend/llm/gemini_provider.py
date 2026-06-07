"""
Google Gemini Provider
"""

import os
from typing import AsyncIterator

import google.generativeai as genai

from .base import BaseLLMProvider, LLMConfig, LLMResponse, Message, ProviderName


class GeminiProvider(BaseLLMProvider):
    name = ProviderName.GEMINI
    default_model = "gemini-1.5-pro"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model or self.default_model
        genai.configure(api_key=self.api_key)
        self._model = genai.GenerativeModel(self.model_name)

    def _to_gemini_messages(
        self, messages: list[Message], system: str | None
    ) -> tuple[str | None, list[dict]]:
        """Convert messages to Gemini format."""
        sys_prompt = system
        history = []
        for m in messages[:-1]:
            role = "user" if m.role == "user" else "model"
            history.append({"role": role, "parts": [m.content]})
        last = messages[-1].content
        if sys_prompt:
            last = f"{sys_prompt}\n\n{last}"
        return last, history

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        cfg = config or LLMConfig()
        last_message, history = self._to_gemini_messages(messages, system)

        chat = self._model.start_chat(history=history)
        generation_config = genai.types.GenerationConfig(
            temperature=cfg.temperature,
            max_output_tokens=cfg.max_tokens,
        )
        response = await chat.send_message_async(
            last_message, generation_config=generation_config
        )

        return LLMResponse(
            content=response.text,
            provider=self.name,
            model=self.model_name,
            input_tokens=response.usage_metadata.prompt_token_count if hasattr(response, "usage_metadata") else 0,
            output_tokens=response.usage_metadata.candidates_token_count if hasattr(response, "usage_metadata") else 0,
        )

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        cfg = config or LLMConfig()
        last_message, history = self._to_gemini_messages(messages, system)
        chat = self._model.start_chat(history=history)
        generation_config = genai.types.GenerationConfig(
            temperature=cfg.temperature,
            max_output_tokens=cfg.max_tokens,
        )
        async for chunk in await chat.send_message_async(
            last_message, generation_config=generation_config, stream=True
        ):
            yield chunk.text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            result = genai.embed_content(
                model="models/text-embedding-004", content=text
            )
            results.append(result["embedding"])
        return results
