"""
Unit tests for the RAG chunking module.
"""

import pytest
from backend.rag.chunking import RecursiveTextSplitter, Chunk
from backend.rag.ingestion import RawDocument


@pytest.fixture
def splitter():
    return RecursiveTextSplitter(chunk_size=200, chunk_overlap=30)


@pytest.fixture
def sample_doc():
    return RawDocument(
        id="test_doc_001",
        source="test.md",
        content="""# Introduction

This is a test document about authentication systems.

## JWT Tokens

JSON Web Tokens are used for stateless authentication. They contain three parts: header, payload, and signature.

The header specifies the algorithm used. The payload contains claims. The signature verifies integrity.

## Session Management

Sessions are stored in Redis. Each session has a TTL of 7 days. Users can have up to 10 concurrent sessions.

## Security Considerations

Always validate token expiry. Never store tokens in localStorage. Use httpOnly cookies instead.
""",
        doc_type="markdown",
        metadata={"filename": "test.md"},
    )


class TestRecursiveTextSplitter:

    def test_short_text_not_split(self, splitter):
        text = "Short text that fits in one chunk."
        chunks = splitter.split_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_split_into_multiple(self, splitter):
        text = ("word " * 100).strip()  # 500 chars
        chunks = splitter.split_text(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= splitter.chunk_size + splitter.chunk_overlap + 10

    def test_empty_text_returns_empty(self, splitter):
        assert splitter.split_text("") == []
        assert splitter.split_text("   ") == []

    def test_split_document_returns_chunks(self, splitter, sample_doc):
        chunks = splitter.split_document(sample_doc)
        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert chunk.doc_id == sample_doc.id
            assert chunk.source == sample_doc.source
            assert len(chunk.content) > 0

    def test_chunk_metadata_populated(self, splitter, sample_doc):
        chunks = splitter.split_document(sample_doc)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert "filename" in chunk.metadata
            assert chunk.metadata["doc_id"] == sample_doc.id

    def test_chunk_ids_unique(self, splitter, sample_doc):
        chunks = splitter.split_document(sample_doc)
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids)), "Chunk IDs must be unique"

    def test_split_preserves_content(self, splitter, sample_doc):
        chunks = splitter.split_document(sample_doc)
        combined = " ".join(c.content for c in chunks)
        # Every meaningful word from original should appear somewhere in chunks
        key_words = ["authentication", "Redis", "signature", "httpOnly"]
        for word in key_words:
            assert word in combined, f"Word '{word}' lost during chunking"

    def test_split_multiple_documents(self, splitter):
        docs = [
            RawDocument(id=f"doc_{i}", source=f"doc{i}.txt", content=f"Document {i} content. " * 20, doc_type="txt", metadata={})
            for i in range(3)
        ]
        chunks = splitter.split_documents(docs)
        assert len(chunks) > 3  # Should produce multiple chunks

    def test_chunk_preview_truncates(self, splitter, sample_doc):
        chunks = splitter.split_document(sample_doc)
        for chunk in chunks:
            assert len(chunk.preview) <= 103  # 100 + "..."
