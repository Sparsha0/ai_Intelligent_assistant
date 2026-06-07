"""
Vector Store - ChromaDB-backed semantic storage and retrieval.
"""

import logging
import os
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings

from .chunking import Chunk

logger = logging.getLogger(__name__)

COLLECTION_NAME = "engineering_knowledge"


@dataclass
class RetrievedChunk:
    """A chunk retrieved from the vector store with relevance score."""
    chunk_id: str
    doc_id: str
    source: str
    content: str
    score: float
    metadata: dict

    @property
    def citation(self) -> str:
        filename = self.metadata.get("filename", self.source)
        chunk_idx = self.metadata.get("chunk_index", "?")
        return f"{filename} (chunk {chunk_idx})"


class VectorStore:
    """
    ChromaDB-backed vector store.
    Swappable: replace with Pinecone, Qdrant, or PGVector in production.
    """

    def __init__(self, persist_dir: str | None = None, embed_fn=None):
        persist_dir = persist_dir or os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
        os.makedirs(persist_dir, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._embed_fn = embed_fn  # Injected embedding function
        logger.info(f"VectorStore ready at {persist_dir}")

    async def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]):
        """Add chunks with pre-computed embeddings."""
        if not chunks:
            return

        ids = [c.id for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = [{**c.metadata, "source": c.source, "doc_id": c.doc_id} for c in chunks]

        # ChromaDB upserts (idempotent)
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info(f"Added/updated {len(chunks)} chunks in vector store")

    async def query(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        filter_metadata: dict | None = None,
    ) -> list[RetrievedChunk]:
        """Semantic search with optional metadata filtering."""
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": min(n_results, self._collection.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if filter_metadata:
            kwargs["where"] = filter_metadata

        results = self._collection.query(**kwargs)

        retrieved = []
        for i, (doc, meta, dist) in enumerate(
            zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ):
            score = 1.0 - dist  # Convert cosine distance to similarity
            retrieved.append(
                RetrievedChunk(
                    chunk_id=results["ids"][0][i],
                    doc_id=meta.get("doc_id", ""),
                    source=meta.get("source", ""),
                    content=doc,
                    score=score,
                    metadata=meta,
                )
            )

        return retrieved

    async def delete_document(self, doc_id: str):
        """Remove all chunks for a document."""
        self._collection.delete(where={"doc_id": doc_id})
        logger.info(f"Deleted document {doc_id} from vector store")

    def count(self) -> int:
        return self._collection.count()

    def list_sources(self) -> list[str]:
        """List all ingested document sources."""
        results = self._collection.get(include=["metadatas"])
        sources = set()
        for meta in results.get("metadatas", []):
            if meta and "source" in meta:
                sources.add(meta["source"])
        return sorted(sources)
