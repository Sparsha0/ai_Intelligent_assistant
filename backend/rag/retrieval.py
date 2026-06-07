"""
RAG Retrieval Pipeline
Semantic search + context-aware answering with source citations.
"""

import logging
from dataclasses import dataclass, field

from llm.base import LLMConfig, Message
from llm.router import LLMRouter
from rag.chunking import RecursiveTextSplitter
from rag.ingestion import DocumentIngester, RawDocument
from rag.vectorstore import RetrievedChunk, VectorStore

logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = 0.35  # Below this score → "I don't know"
MAX_CONTEXT_CHUNKS = 6

RAG_SYSTEM_PROMPT = """You are a precise engineering knowledge assistant.
Answer ONLY based on the provided context below.
If the context does not contain enough information, say exactly: "I don't have enough information in the knowledge base to answer this question."
Always cite your sources using [Source: filename] notation at the end of relevant sentences.
Be concise, technical, and accurate."""


@dataclass
class RAGResponse:
    """Response from the RAG pipeline."""
    answer: str
    sources: list[str]
    chunks_used: int
    max_relevance_score: float
    grounded: bool  # False if below threshold
    token_usage: dict = field(default_factory=dict)


class RAGPipeline:
    """
    Full RAG pipeline:
    1. Embed query
    2. Retrieve relevant chunks
    3. Build context
    4. Generate grounded answer
    5. Return with citations
    """

    def __init__(self, vector_store: VectorStore, llm_router: LLMRouter):
        self.vector_store = vector_store
        self.llm = llm_router
        self.ingester = DocumentIngester()
        self.splitter = RecursiveTextSplitter(chunk_size=512, chunk_overlap=64)

    async def ingest(self, doc: RawDocument) -> int:
        """Ingest a document into the vector store. Returns chunk count."""
        chunks = self.splitter.split_document(doc)
        if not chunks:
            return 0

        texts = [c.content for c in chunks]
        embeddings = await self.llm.embed(texts)
        await self.vector_store.add_chunks(chunks, embeddings)
        logger.info(f"Ingested {doc.source}: {len(chunks)} chunks")
        return len(chunks)

    async def ingest_file(self, path: str) -> int:
        doc = self.ingester.ingest_file(path)
        return await self.ingest(doc)

    async def ingest_text(self, text: str, source: str, metadata: dict | None = None) -> int:
        doc = self.ingester.ingest_text(text, source, metadata=metadata)
        return await self.ingest(doc)

    async def query(
        self,
        question: str,
        n_results: int = MAX_CONTEXT_CHUNKS,
        threshold: float = RELEVANCE_THRESHOLD,
    ) -> RAGResponse:
        """Query the knowledge base and return a grounded answer."""
        # 1. Embed the question
        query_embedding = (await self.llm.embed([question]))[0]

        # 2. Retrieve relevant chunks
        chunks = await self.vector_store.query(query_embedding, n_results=n_results)

        # 3. Filter by relevance threshold
        relevant = [c for c in chunks if c.score >= threshold]

        if not relevant:
            return RAGResponse(
                answer="I don't have enough information in the knowledge base to answer this question.",
                sources=[],
                chunks_used=0,
                max_relevance_score=max((c.score for c in chunks), default=0.0),
                grounded=False,
            )

        # 4. Build context string with source labels
        context_parts = []
        for i, chunk in enumerate(relevant[:MAX_CONTEXT_CHUNKS]):
            source_label = chunk.metadata.get("filename", chunk.source)
            context_parts.append(
                f"[Context {i+1} | Source: {source_label} | Relevance: {chunk.score:.2f}]\n{chunk.content}"
            )
        context = "\n\n---\n\n".join(context_parts)

        # 5. Generate answer
        prompt = f"""Context from knowledge base:

{context}

---

Question: {question}

Answer based strictly on the context above:"""

        response = await self.llm.complete(
            messages=[Message(role="user", content=prompt)],
            system=RAG_SYSTEM_PROMPT,
            config=LLMConfig(temperature=0.1, max_tokens=1024),
            task_type="default",
        )

        # 6. Collect unique sources
        sources = list({c.citation for c in relevant})

        return RAGResponse(
            answer=response.content,
            sources=sources,
            chunks_used=len(relevant),
            max_relevance_score=max(c.score for c in relevant),
            grounded=True,
            token_usage={
                "input": response.input_tokens,
                "output": response.output_tokens,
            },
        )

    def stats(self) -> dict:
        return {
            "total_chunks": self.vector_store.count(),
            "sources": self.vector_store.list_sources(),
        }
