"""
Text Chunking Module
Recursive text splitter that preserves semantic boundaries.
"""

from dataclasses import dataclass, field
from typing import List

from .ingestion import RawDocument


@dataclass
class Chunk:
    """A text chunk ready for embedding."""
    id: str
    doc_id: str
    source: str
    content: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)

    @property
    def preview(self) -> str:
        return self.content[:100] + "..." if len(self.content) > 100 else self.content


class RecursiveTextSplitter:
    """
    Splits documents into chunks using recursive character splitting.
    Respects natural boundaries: paragraphs → sentences → words.
    """

    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", ", ", " ", ""]

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        separators: list[str] | None = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self.DEFAULT_SEPARATORS

    def split_text(self, text: str) -> list[str]:
        """Split text into chunks recursively."""
        return self._split_recursive(text, self.separators)

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        if not text.strip():
            return []

        if len(text) <= self.chunk_size:
            return [text.strip()]

        separator = separators[0] if separators else ""
        remaining_separators = separators[1:] if len(separators) > 1 else []

        # Try splitting by current separator
        splits = text.split(separator) if separator else list(text)
        chunks = []
        current = ""

        for split in splits:
            piece = (current + separator + split).strip() if current else split.strip()

            if len(piece) <= self.chunk_size:
                current = piece
            else:
                # Save what we have
                if current:
                    chunks.append(current)

                # If the split itself is too large, recurse
                if len(split) > self.chunk_size and remaining_separators:
                    sub_chunks = self._split_recursive(split, remaining_separators)
                    # Add overlap
                    if chunks and sub_chunks:
                        overlap = chunks[-1][-self.chunk_overlap:]
                        sub_chunks[0] = overlap + " " + sub_chunks[0]
                    chunks.extend(sub_chunks)
                    current = ""
                else:
                    current = split.strip()

        if current:
            chunks.append(current)

        # Add overlap between chunks
        return self._add_overlap(chunks)

    def _add_overlap(self, chunks: list[str]) -> list[str]:
        if len(chunks) <= 1:
            return chunks
        result = [chunks[0]]
        for i in range(1, len(chunks)):
            overlap = chunks[i - 1][-self.chunk_overlap:]
            result.append(overlap + " " + chunks[i])
        return result

    def split_document(self, doc: RawDocument) -> list[Chunk]:
        """Split a document into chunks."""
        texts = self.split_text(doc.content)
        chunks = []

        for i, text in enumerate(texts):
            if not text.strip():
                continue
            chunk_id = f"{doc.id}_chunk_{i}"
            chunks.append(
                Chunk(
                    id=chunk_id,
                    doc_id=doc.id,
                    source=doc.source,
                    content=text.strip(),
                    chunk_index=i,
                    metadata={
                        **doc.metadata,
                        "chunk_index": i,
                        "total_chunks": len(texts),
                        "doc_id": doc.id,
                    },
                )
            )

        return chunks

    def split_documents(self, docs: list[RawDocument]) -> list[Chunk]:
        """Split multiple documents."""
        all_chunks = []
        for doc in docs:
            chunks = self.split_document(doc)
            all_chunks.extend(chunks)
        return all_chunks
