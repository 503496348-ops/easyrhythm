"""
Document loader (AtomCollide-智械工坊)

Loads documents from various sources into a normalized Document format
for ingestion into the vector store.

Supported sources:
- Plain text files (.txt)
- Markdown files (.md)
- PDF files (.pdf) via PyPDF2
- URLs via httpx + basic HTML extraction
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """Normalized document representation."""

    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    doc_id: str = ""

    def __post_init__(self):
        if not self.doc_id:
            self.doc_id = hashlib.md5(self.content.encode()).hexdigest()[:12]

    @property
    def chunk_count(self) -> int:
        return self.metadata.get("chunk_count", 0)


@dataclass
class DocumentChunk:
    """A chunk of a document for embedding and retrieval."""

    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_id: str = ""
    doc_id: str = ""
    index: int = 0

    def __post_init__(self):
        if not self.chunk_id:
            self.chunk_id = f"{self.doc_id}_{self.index}"


class DocumentLoader:
    """
    Loads and chunks documents from various sources.

    Usage:
        loader = DocumentLoader(chunk_size=500, chunk_overlap=50)
        docs = loader.load_file("/path/to/doc.pdf")
        chunks = loader.load_and_chunk("/path/to/doc.md")
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    # ── Loading ───────────────────────────────────────────────────────

    def load_file(self, path: str) -> List[Document]:
        """Load a single file and return documents."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")

        suffix = p.suffix.lower()
        if suffix in (".txt", ".md", ".markdown"):
            return self._load_text(p)
        elif suffix == ".pdf":
            return self._load_pdf(p)
        else:
            # Try as text
            return self._load_text(p)

    def load_directory(self, path: str, extensions: Optional[List[str]] = None) -> List[Document]:
        """Load all matching files from a directory."""
        p = Path(path)
        if not p.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        extensions = extensions or [".txt", ".md", ".markdown", ".pdf"]
        docs = []
        for ext in extensions:
            for f in p.rglob(f"*{ext}"):
                try:
                    docs.extend(self.load_file(str(f)))
                except Exception:
                    logger.warning(f"Failed to load: {f}")
        return docs

    async def load_url(self, url: str) -> List[Document]:
        """Load content from a URL."""
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        text = resp.text

        # Basic HTML stripping
        if "html" in content_type:
            text = self._strip_html(text)

        doc = Document(
            content=text,
            metadata={
                "source": url,
                "content_type": content_type,
                "loaded_at": time.time(),
            },
        )
        return [doc]

    async def load_urls(self, urls: List[str]) -> List[Document]:
        """Load content from multiple URLs."""
        docs = []
        for url in urls:
            try:
                docs.extend(await self.load_url(url))
            except Exception:
                logger.warning(f"Failed to load URL: {url}")
        return docs

    # ── Chunking ──────────────────────────────────────────────────────

    def chunk_document(self, doc: Document) -> List[DocumentChunk]:
        """Split a document into chunks for embedding."""
        text = doc.content.strip()
        if not text:
            return []

        # Try to split on paragraph boundaries first
        paragraphs = re.split(r"\n\s*\n", text)
        chunks: List[DocumentChunk] = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If adding this paragraph exceeds chunk_size, finalize current chunk
            if current_chunk and len(current_chunk) + len(para) + 1 > self.chunk_size:
                chunks.append(self._make_chunk(current_chunk, doc.doc_id, len(chunks)))
                # Keep overlap from end of previous chunk
                if self.chunk_overlap > 0:
                    current_chunk = current_chunk[-self.chunk_overlap:] + "\n" + para
                else:
                    current_chunk = para
            else:
                current_chunk = current_chunk + "\n" + para if current_chunk else para

            # If single paragraph exceeds chunk_size, split by sentences
            while len(current_chunk) > self.chunk_size:
                split_point = self._find_split_point(current_chunk, self.chunk_size)
                chunks.append(self._make_chunk(current_chunk[:split_point], doc.doc_id, len(chunks)))
                current_chunk = current_chunk[split_point - self.chunk_overlap:].strip()

        if current_chunk.strip():
            chunks.append(self._make_chunk(current_chunk.strip(), doc.doc_id, len(chunks)))

        doc.metadata["chunk_count"] = len(chunks)
        return chunks

    def load_and_chunk(self, path: str) -> List[DocumentChunk]:
        """Load a file and return chunks."""
        docs = self.load_file(path)
        all_chunks = []
        for doc in docs:
            all_chunks.extend(self.chunk_document(doc))
        return all_chunks

    async def load_url_and_chunk(self, url: str) -> List[DocumentChunk]:
        """Load a URL and return chunks."""
        docs = await self.load_url(url)
        all_chunks = []
        for doc in docs:
            all_chunks.extend(self.chunk_document(doc))
        return all_chunks

    # ── Internal helpers ──────────────────────────────────────────────

    def _load_text(self, path: Path) -> List[Document]:
        text = path.read_text(encoding="utf-8", errors="replace")
        return [Document(
            content=text,
            metadata={"source": str(path), "filename": path.name, "loaded_at": time.time()},
        )]

    def _load_pdf(self, path: Path) -> List[Document]:
        """Load a PDF file using PyPDF2."""
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(path))
            pages = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(Document(
                        content=text,
                        metadata={
                            "source": str(path),
                            "filename": path.name,
                            "page": i + 1,
                            "loaded_at": time.time(),
                        },
                    ))
            return pages if pages else [Document(content="", metadata={"source": str(path)})]
        except ImportError:
            logger.warning("PyPDF2 not installed, treating PDF as text")
            return self._load_text(path)

    @staticmethod
    def _strip_html(html: str) -> str:
        """Basic HTML tag stripping."""
        # Remove scripts and styles
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Replace <br> and block elements with newlines
        html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        html = re.sub(r"</(p|div|h[1-6]|li|tr)>", "\n", html, flags=re.IGNORECASE)
        # Remove remaining tags
        html = re.sub(r"<[^>]+>", "", html)
        # Decode entities
        html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        html = html.replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
        # Collapse whitespace
        html = re.sub(r"\n\s*\n", "\n\n", html)
        return html.strip()

    @staticmethod
    def _find_split_point(text: str, max_len: int) -> int:
        """Find a good split point (sentence or word boundary)."""
        # Try sentence boundary
        for delim in [". ", "! ", "? ", "\n"]:
            idx = text.rfind(delim, 0, max_len)
            if idx > max_len // 2:
                return idx + len(delim)
        # Fall back to word boundary
        idx = text.rfind(" ", 0, max_len)
        if idx > 0:
            return idx + 1
        return max_len

    @staticmethod
    def _make_chunk(content: str, doc_id: str, index: int) -> DocumentChunk:
        return DocumentChunk(
            content=content.strip(),
            doc_id=doc_id,
            index=index,
            metadata={"doc_id": doc_id, "index": index},
        )
