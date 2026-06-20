"""
RAG Retriever (AtomCollide-智械工坊)

Orchestrates the full RAG pipeline:
1. Load documents → chunk → embed → store
2. Query → embed → retrieve top-k → format context for injection

Inspired by Dify's retrieval pattern: when a query comes in, the retriever
finds the most relevant chunks and formats them as context that can be
injected into an agent's system prompt or as tool output.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .embedder import TextEmbedder, get_embedder
from .loader import DocumentChunk, DocumentLoader
from .store import VectorStore, VectorRecord, SearchResult, get_vector_store

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Result of a RAG retrieval query."""

    query: str = ""
    chunks: List[SearchResult] = field(default_factory=list)
    context_text: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    retrieval_time_ms: float = 0

    @property
    def has_results(self) -> bool:
        return len(self.chunks) > 0


class RAGRetriever:
    """
    Full RAG retriever that manages the document lifecycle and query pipeline.

    Usage:
        embedder = get_embedder("auto")
        store = get_vector_store("auto")
        retriever = RAGRetriever(embedder=embedder, store=store)

        # Ingest documents
        await retriever.ingest_file("/path/to/doc.md")
        await retriever.ingest_text("Important policy text...", source="policy_v1")

        # Query
        result = await retriever.retrieve("What is the cancellation policy?", top_k=3)
        print(result.context_text)
    """

    def __init__(
        self,
        embedder: Optional[TextEmbedder] = None,
        store: Optional[VectorStore] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        score_threshold: float = 0.3,
    ) -> None:
        self.embedder = embedder or get_embedder()
        self.store = store or get_vector_store(dimension=self.embedder.dimensions)
        self.loader = DocumentLoader(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.score_threshold = score_threshold

    # ── Ingestion ─────────────────────────────────────────────────────

    async def ingest_text(
        self,
        text: str,
        source: str = "manual",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Ingest raw text into the knowledge base.

        Returns: Number of chunks added
        """
        from .loader import Document

        doc = Document(
            content=text,
            metadata={**(metadata or {}), "source": source, "loaded_at": time.time()},
        )
        chunks = self.loader.chunk_document(doc)
        return await self._embed_and_store(chunks)

    async def ingest_file(self, path: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Ingest a file into the knowledge base.

        Returns: Number of chunks added
        """
        docs = self.loader.load_file(path)
        total_chunks = 0
        for doc in docs:
            if metadata:
                doc.metadata.update(metadata)
            chunks = self.loader.chunk_document(doc)
            total_chunks += await self._embed_and_store(chunks)
        return total_chunks

    async def ingest_url(self, url: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Ingest content from a URL into the knowledge base.

        Returns: Number of chunks added
        """
        docs = await self.loader.load_url(url)
        total_chunks = 0
        for doc in docs:
            if metadata:
                doc.metadata.update(metadata)
            chunks = self.loader.chunk_document(doc)
            total_chunks += await self._embed_and_store(chunks)
        return total_chunks

    async def ingest_chunks(self, chunks: List[DocumentChunk]) -> int:
        """Ingest pre-formed chunks directly."""
        return await self._embed_and_store(chunks)

    async def _embed_and_store(self, chunks: List[DocumentChunk]) -> int:
        """Embed chunks and store them."""
        if not chunks:
            return 0

        texts = [c.content for c in chunks]
        embeddings = await self.embedder.embed_batch(texts)

        records = []
        for chunk, embedding in zip(chunks, embeddings):
            records.append(VectorRecord(
                id=chunk.chunk_id,
                vector=embedding,
                text=chunk.content,
                metadata=chunk.metadata,
                doc_id=chunk.doc_id,
            ))

        return self.store.add_batch(records)

    # ── Retrieval ─────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filter_doc_ids: Optional[List[str]] = None,
        score_threshold: Optional[float] = None,
    ) -> RetrievalResult:
        """
        Retrieve the most relevant chunks for a query.

        Args:
            query: The search query
            top_k: Number of results to return
            filter_doc_ids: Optional list of doc_ids to search within
            score_threshold: Minimum similarity score (default: self.score_threshold)

        Returns:
            RetrievalResult with chunks and formatted context
        """
        start = time.time()
        threshold = score_threshold if score_threshold is not None else self.score_threshold

        # Embed the query
        query_embedding = await self.embedder.embed(query)

        # Search the vector store
        results = self.store.search(query_embedding, top_k=top_k + 5)  # over-fetch for filtering

        # Apply score threshold
        filtered = [r for r in results if r.score >= threshold]

        # Apply doc_id filter if specified
        if filter_doc_ids:
            filtered = [r for r in filtered if r.record.doc_id in filter_doc_ids]

        # Take top_k after filtering
        filtered = filtered[:top_k]

        # Format context
        context_parts = []
        sources = []
        for i, result in enumerate(filtered):
            context_parts.append(
                f"[{i + 1}] (score: {result.score:.3f}) {result.record.text}"
            )
            sources.append({
                "chunk_id": result.record.id,
                "doc_id": result.record.doc_id,
                "score": result.score,
                "source": result.record.metadata.get("source", ""),
                "preview": result.record.text[:200],
            })

        context_text = "\n\n".join(context_parts)
        elapsed_ms = (time.time() - start) * 1000

        return RetrievalResult(
            query=query,
            chunks=filtered,
            context_text=context_text,
            sources=sources,
            retrieval_time_ms=elapsed_ms,
        )

    async def format_context_for_agent(
        self,
        query: str,
        top_k: int = 3,
        max_context_length: int = 2000,
    ) -> str:
        """
        Retrieve and format context for injection into an agent prompt.

        Returns a formatted string like:
        ```
        [Knowledge Base Context]
        Retrieved 3 relevant passages:

        [1] Passage text here...
        [2] Another passage...
        [3] Yet another...

        Use the above context to inform your response.
        ```
        """
        result = await self.retrieve(query, top_k=top_k)

        if not result.has_results:
            return ""

        # Truncate if needed
        context = result.context_text
        if len(context) > max_context_length:
            context = context[:max_context_length] + "..."

        return (
            f"[Knowledge Base Context]\n"
            f"Retrieved {len(result.chunks)} relevant passage(s) "
            f"(query time: {result.retrieval_time_ms:.0f}ms):\n\n"
            f"{context}\n\n"
            f"Use the above context to inform your response when relevant."
        )

    # ── Management ────────────────────────────────────────────────────

    def delete_document(self, doc_id: str) -> int:
        """Delete all chunks for a document."""
        return self.store.delete_by_doc(doc_id)

    def clear(self) -> None:
        """Clear the entire knowledge base."""
        self.store.clear()

    @property
    def total_chunks(self) -> int:
        return self.store.count()
