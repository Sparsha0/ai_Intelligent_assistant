"""
Integration tests for the full RAG pipeline.
Runs without real API keys using mock embeddings and mock LLM.
"""

import os
import pytest
import tempfile

os.environ.setdefault("CHROMA_PERSIST_DIR", tempfile.mkdtemp())

from backend.rag.retrieval import RAGPipeline
from backend.rag.vectorstore import VectorStore
from backend.llm.router import LLMRouter


@pytest.fixture
def temp_chroma(tmp_path):
    return str(tmp_path / "chroma_test")


@pytest.fixture
def mock_router(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return LLMRouter()


@pytest.fixture
def rag_pipeline(temp_chroma, mock_router):
    vs = VectorStore(persist_dir=temp_chroma)
    return RAGPipeline(vector_store=vs, llm_router=mock_router)


SAMPLE_DOCS = [
    (
        "JWT tokens expire after 15 minutes. Refresh tokens expire after 7 days. "
        "Always validate token expiry on the server side. Never trust client-reported expiry.",
        "auth-policy.md",
    ),
    (
        "Redis is used for session storage. Each session has a TTL of 86400 seconds. "
        "Maximum 10 concurrent sessions per user. Sessions invalidated on password change.",
        "session-management.md",
    ),
    (
        "Rate limiting: 10 login attempts per minute per IP. "
        "Exponential backoff applied after 5 failures. Account lockout after 20 failures in 1 hour.",
        "rate-limiting.md",
    ),
]


class TestRAGPipelineIntegration:

    @pytest.mark.asyncio
    async def test_ingest_text_returns_chunk_count(self, rag_pipeline):
        chunks = await rag_pipeline.ingest_text(
            "This is sample documentation about authentication.",
            "test.md",
        )
        assert chunks > 0

    @pytest.mark.asyncio
    async def test_ingest_multiple_docs(self, rag_pipeline):
        total = 0
        for content, source in SAMPLE_DOCS:
            n = await rag_pipeline.ingest_text(content, source)
            total += n
        assert total > 0
        stats = rag_pipeline.stats()
        assert stats["total_chunks"] > 0

    @pytest.mark.asyncio
    async def test_query_returns_response(self, rag_pipeline):
        await rag_pipeline.ingest_text(SAMPLE_DOCS[0][0], SAMPLE_DOCS[0][1])
        result = await rag_pipeline.query("How long do JWT tokens last?")
        assert result.answer
        assert isinstance(result.sources, list)

    @pytest.mark.asyncio
    async def test_empty_knowledge_base_returns_dont_know(self, temp_chroma, mock_router):
        """Empty KB should return 'I don't know' style response."""
        vs = VectorStore(persist_dir=temp_chroma + "_empty")
        pipeline = RAGPipeline(vector_store=vs, llm_router=mock_router)
        result = await pipeline.query("What is the meaning of life?")
        # Either grounded=False or the mock says it doesn't know
        assert result.chunks_used == 0 or result.grounded is False

    @pytest.mark.asyncio
    async def test_stats_reflect_ingested_docs(self, rag_pipeline):
        for content, source in SAMPLE_DOCS:
            await rag_pipeline.ingest_text(content, source)

        stats = rag_pipeline.stats()
        assert "total_chunks" in stats
        assert "sources" in stats
        assert stats["total_chunks"] > 0
        assert len(stats["sources"]) > 0

    @pytest.mark.asyncio
    async def test_ingest_file_markdown(self, rag_pipeline, tmp_path):
        md_file = tmp_path / "test_doc.md"
        md_file.write_text("# Test\n\nThis is a markdown document about deployment pipelines.\n\n"
                           "## CI/CD\n\nWe use GitHub Actions for continuous integration.\n")
        chunks = await rag_pipeline.ingest_file(str(md_file))
        assert chunks > 0

    @pytest.mark.asyncio
    async def test_query_sources_populated(self, rag_pipeline):
        await rag_pipeline.ingest_text(SAMPLE_DOCS[1][0], SAMPLE_DOCS[1][1], metadata={"filename": SAMPLE_DOCS[1][1]})
        result = await rag_pipeline.query("How does Redis session storage work?")
        if result.grounded:
            assert len(result.sources) > 0

    @pytest.mark.asyncio
    async def test_relevance_score_in_range(self, rag_pipeline):
        await rag_pipeline.ingest_text(SAMPLE_DOCS[0][0], SAMPLE_DOCS[0][1])
        result = await rag_pipeline.query("JWT expiry policy")
        assert 0.0 <= result.max_relevance_score <= 1.0
