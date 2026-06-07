"""
LLM Router - Provider abstraction with retry, fallback, and routing logic.
"""

import asyncio
import logging
import os
import random
from typing import AsyncIterator

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .anthropic_provider import AnthropicProvider
from .base import BaseLLMProvider, LLMConfig, LLMResponse, Message, ProviderName
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


TASK_ROUTING: dict[str, list[ProviderName]] = {
    # Tasks where we prefer certain providers
    "code_analysis": [ProviderName.ANTHROPIC, ProviderName.OPENAI],
    "summarization": [ProviderName.ANTHROPIC, ProviderName.GEMINI],
    "structured_output": [ProviderName.OPENAI, ProviderName.ANTHROPIC],
    "research": [ProviderName.GEMINI, ProviderName.ANTHROPIC],
    "default": [ProviderName.ANTHROPIC, ProviderName.OPENAI, ProviderName.GEMINI],
}


class LLMRouter:
    """
    Routes LLM requests to the appropriate provider with:
    - Configurable primary provider
    - Automatic fallback chain
    - Retry with exponential backoff
    - Task-based routing
    - Token usage tracking
    """

    def __init__(self):
        self._providers: dict[ProviderName, BaseLLMProvider] = {}
        self._total_tokens: int = 0
        self._primary = ProviderName(os.getenv("LLM_PROVIDER", "anthropic"))
        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize all configured providers."""
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                self._providers[ProviderName.ANTHROPIC] = AnthropicProvider()
                logger.info("Anthropic provider initialized")
            except Exception as e:
                logger.warning(f"Failed to init Anthropic: {e}")

        if os.getenv("OPENAI_API_KEY"):
            try:
                self._providers[ProviderName.OPENAI] = OpenAIProvider()
                logger.info("OpenAI provider initialized")
            except Exception as e:
                logger.warning(f"Failed to init OpenAI: {e}")

        if os.getenv("GEMINI_API_KEY"):
            try:
                self._providers[ProviderName.GEMINI] = GeminiProvider()
                logger.info("Gemini provider initialized")
            except Exception as e:
                logger.warning(f"Failed to init Gemini: {e}")

        if not self._providers:
            logger.warning("No real LLM providers configured — using mock provider")
            self._providers[ProviderName.ANTHROPIC] = MockProvider()

    def _get_fallback_chain(self, task_type: str = "default") -> list[BaseLLMProvider]:
        """Build ordered list of providers to try."""
        preferred = TASK_ROUTING.get(task_type, TASK_ROUTING["default"])

        # Start with primary if available
        chain = []
        if self._primary in self._providers:
            chain.append(self._providers[self._primary])

        # Add preferred providers for task
        for name in preferred:
            if name in self._providers and name != self._primary:
                chain.append(self._providers[name])

        # Add any remaining providers
        for name, provider in self._providers.items():
            if provider not in chain:
                chain.append(provider)

        return chain

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        config: LLMConfig | None = None,
        task_type: str = "default",
    ) -> LLMResponse:
        """Complete with automatic retry and fallback."""
        chain = self._get_fallback_chain(task_type)
        last_error: Exception | None = None

        for provider in chain:
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=1, min=1, max=10),
                    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
                    reraise=True,
                ):
                    with attempt:
                        response = await provider.complete(messages, system, config)
                        self._total_tokens += response.total_tokens
                        logger.info(
                            f"LLM complete via {provider.name} | "
                            f"tokens: {response.total_tokens}"
                        )
                        return response
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed: {e}, trying next...")
                last_error = e
                continue

        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        config: LLMConfig | None = None,
        task_type: str = "default",
    ) -> AsyncIterator[str]:
        """Stream with fallback."""
        chain = self._get_fallback_chain(task_type)
        for provider in chain:
            try:
                async for token in provider.stream(messages, system, config):
                    yield token
                return
            except Exception as e:
                logger.warning(f"Stream provider {provider.name} failed: {e}")
                continue
        raise RuntimeError("All stream providers failed")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings, preferring OpenAI, then Gemini."""
        for name in [ProviderName.OPENAI, ProviderName.GEMINI]:
            if name in self._providers:
                try:
                    return await self._providers[name].embed(texts)
                except Exception as e:
                    logger.warning(f"Embed via {name} failed: {e}")
        # Fallback: deterministic mock embeddings (for testing without API keys)
        return self._mock_embeddings(texts)

    def _mock_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Deterministic mock embeddings based on text hash (for dev/testing)."""
        import hashlib
        results = []
        for text in texts:
            seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
            rng = random.Random(seed)
            results.append([rng.gauss(0, 1) for _ in range(1536)])
        return results

    @property
    def total_tokens_used(self) -> int:
        return self._total_tokens

    @property
    def available_providers(self) -> list[str]:
        return [p.name for p in self._providers.keys()]


class MockProvider(BaseLLMProvider):
    """Mock provider for testing without API keys."""
    name = ProviderName.ANTHROPIC
    default_model = "mock-model"

    async def complete(self, messages, system=None, config=None) -> LLMResponse:
        last_msg = messages[-1].content if messages else ""
        return LLMResponse(
            content=f"[MOCK RESPONSE] I received: '{last_msg[:100]}...' — Configure an LLM API key for real responses.",
            provider="mock",
            model="mock-model",
            input_tokens=len(last_msg) // 4,
            output_tokens=20,
        )

    async def stream(self, messages, system=None, config=None) -> AsyncIterator[str]:
        response = await self.complete(messages, system, config)
        for word in response.content.split():
            yield word + " "
            await asyncio.sleep(0.05)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]


# Singleton router instance
_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
