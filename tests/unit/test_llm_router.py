"""
Unit tests for the LLM router and mock provider.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.llm.router import LLMRouter, MockProvider
from backend.llm.base import LLMResponse, Message, LLMConfig, ProviderName


@pytest.fixture
def mock_provider():
    return MockProvider()


@pytest.fixture
def router_no_keys(monkeypatch):
    """Router with no real API keys — uses mock provider."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return LLMRouter()


class TestMockProvider:

    @pytest.mark.asyncio
    async def test_complete_returns_response(self, mock_provider):
        messages = [Message(role="user", content="Hello")]
        response = await mock_provider.complete(messages)
        assert isinstance(response, LLMResponse)
        assert response.content
        assert response.provider == "mock"

    @pytest.mark.asyncio
    async def test_complete_echoes_message(self, mock_provider):
        messages = [Message(role="user", content="What is JWT?")]
        response = await mock_provider.complete(messages)
        assert "JWT" in response.content or "MOCK" in response.content

    @pytest.mark.asyncio
    async def test_stream_yields_tokens(self, mock_provider):
        messages = [Message(role="user", content="ping")]
        tokens = []
        async for token in mock_provider.stream(messages):
            tokens.append(token)
        assert len(tokens) > 0
        combined = "".join(tokens)
        assert len(combined) > 0

    @pytest.mark.asyncio
    async def test_embed_returns_correct_shape(self, mock_provider):
        texts = ["hello world", "test text"]
        embeddings = await mock_provider.embed(texts)
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 1536
        assert len(embeddings[1]) == 1536

    @pytest.mark.asyncio
    async def test_token_counts_nonzero(self, mock_provider):
        messages = [Message(role="user", content="This is a longer message with many words.")]
        response = await mock_provider.complete(messages)
        assert response.input_tokens > 0
        assert response.output_tokens > 0


class TestLLMRouter:

    def test_router_initializes_with_mock(self, router_no_keys):
        assert len(router_no_keys._providers) > 0

    @pytest.mark.asyncio
    async def test_complete_returns_response(self, router_no_keys):
        messages = [Message(role="user", content="Hello")]
        response = await router_no_keys.complete(messages)
        assert isinstance(response, LLMResponse)
        assert response.content

    @pytest.mark.asyncio
    async def test_token_tracking(self, router_no_keys):
        initial = router_no_keys.total_tokens_used
        await router_no_keys.complete([Message(role="user", content="test")])
        assert router_no_keys.total_tokens_used > initial

    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self, router_no_keys):
        embeddings = await router_no_keys.embed(["hello", "world"])
        assert len(embeddings) == 2
        assert all(len(e) == 1536 for e in embeddings)

    def test_mock_embeddings_deterministic(self, router_no_keys):
        """Same text should always produce same embedding."""
        e1 = router_no_keys._mock_embeddings(["test text"])
        e2 = router_no_keys._mock_embeddings(["test text"])
        assert e1 == e2

    def test_mock_embeddings_differ_by_text(self, router_no_keys):
        """Different texts should produce different embeddings."""
        e1 = router_no_keys._mock_embeddings(["hello world"])
        e2 = router_no_keys._mock_embeddings(["goodbye moon"])
        assert e1 != e2

    def test_available_providers_listed(self, router_no_keys):
        providers = router_no_keys.available_providers
        assert isinstance(providers, list)
        assert len(providers) > 0

    @pytest.mark.asyncio
    async def test_stream_yields_content(self, router_no_keys):
        tokens = []
        async for token in router_no_keys.stream([Message(role="user", content="hi")]):
            tokens.append(token)
        assert len(tokens) > 0

    @pytest.mark.asyncio
    async def test_fallback_on_provider_failure(self):
        """Router should fall back when primary provider fails."""
        router = LLMRouter()

        # Inject a failing provider as primary
        failing = MockProvider()
        async def fail(*args, **kwargs):
            raise ConnectionError("Simulated failure")
        failing.complete = fail

        working = MockProvider()
        router._providers = {
            ProviderName.ANTHROPIC: failing,
            ProviderName.OPENAI: working,
        }
        router._primary = ProviderName.ANTHROPIC

        # Should fall back to OpenAI (working)
        response = await router.complete([Message(role="user", content="test")])
        assert response.content
