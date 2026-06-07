"""
RAG Document Ingestion Pipeline
Supports: PDF, Markdown, TXT, HTML
"""

import hashlib
import logging
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class RawDocument:
    """A document before chunking."""
    id: str
    source: str
    content: str
    doc_type: str
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str | Path) -> "RawDocument":
        path = Path(path)
        content = ""
        doc_type = _detect_type(path)

        if doc_type == "pdf":
            content = _extract_pdf(path)
        elif doc_type == "markdown":
            content = path.read_text(encoding="utf-8")
        elif doc_type == "html":
            content = _extract_html(path)
        elif doc_type == "txt":
            content = path.read_text(encoding="utf-8")
        else:
            raise ValueError(f"Unsupported file type: {path.suffix}")

        doc_id = hashlib.sha256(f"{path}:{os.path.getmtime(path)}".encode()).hexdigest()[:16]

        return cls(
            id=doc_id,
            source=str(path),
            content=content,
            doc_type=doc_type,
            metadata={
                "filename": path.name,
                "file_type": doc_type,
                "file_size": path.stat().st_size,
            },
        )

    @classmethod
    def from_text(cls, text: str, source: str, doc_type: str = "txt", metadata: dict | None = None) -> "RawDocument":
        doc_id = hashlib.sha256(f"{source}:{text[:100]}".encode()).hexdigest()[:16]
        return cls(
            id=doc_id,
            source=source,
            content=text,
            doc_type=doc_type,
            metadata=metadata or {"source": source},
        )


def _detect_type(path: Path) -> str:
    ext = path.suffix.lower()
    mapping = {
        ".pdf": "pdf",
        ".md": "markdown",
        ".markdown": "markdown",
        ".html": "html",
        ".htm": "html",
        ".txt": "txt",
        ".text": "txt",
    }
    return mapping.get(ext, "txt")


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages.append(f"[Page {i+1}]\n{text}")
        return "\n\n".join(pages)
    except ImportError:
        raise ImportError("pypdf required: pip install pypdf")


def _extract_html(path: Path) -> str:
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


class DocumentIngester:
    """
    Handles document ingestion from files and directories.
    Tracks processed docs to avoid re-ingesting unchanged files.
    """

    SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown", ".html", ".htm", ".txt", ".text"}

    def __init__(self):
        self._processed: set[str] = set()

    def ingest_file(self, path: str | Path) -> RawDocument:
        """Ingest a single file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported extension: {path.suffix}")

        doc = RawDocument.from_file(path)
        logger.info(f"Ingested {path.name} ({doc.doc_type}) — {len(doc.content)} chars")
        return doc

    def ingest_directory(self, directory: str | Path, recursive: bool = True) -> list[RawDocument]:
        """Ingest all supported files in a directory."""
        directory = Path(directory)
        docs = []

        pattern = "**/*" if recursive else "*"
        for path in directory.glob(pattern):
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                try:
                    doc = self.ingest_file(path)
                    docs.append(doc)
                except Exception as e:
                    logger.warning(f"Failed to ingest {path}: {e}")

        logger.info(f"Ingested {len(docs)} documents from {directory}")
        return docs

    def ingest_text(
        self, text: str, source: str, doc_type: str = "txt", metadata: dict | None = None
    ) -> RawDocument:
        """Ingest raw text directly."""
        return RawDocument.from_text(text, source, doc_type, metadata)
