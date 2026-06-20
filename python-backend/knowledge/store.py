"""
Vector store abstraction (AtomCollide-智械工坊)

Provides vector storage and similarity search with pluggable backends:
- InMemoryVectorStore: Simple cosine similarity search in memory
- FAISSVectorStore: High-performance FAISS index (optional dependency)

Pattern inspired by Dify's knowledge base: documents are chunked,
embedded, stored, and retrieved by semantic similarity.
"""

from __future__ import annotations

import logging
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class VectorRecord:
    """A single vector record in the store."""

    id: str = ""
    vector: List[float] = field(default_factory=list)
    text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    doc_id: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class SearchResult:
    """A single search result with similarity score."""

    record: VectorRecord = field(default_factory=VectorRecord)
    score: float = 0.0


class VectorStore(ABC):
    """Abstract vector store interface."""

    @abstractmethod
    def add(self, record: VectorRecord) -> None:
        """Add a single record to the store."""
        ...

    def add_batch(self, records: List[VectorRecord]) -> int:
        """Add multiple records. Returns count added."""
        count = 0
        for r in records:
            self.add(r)
            count += 1
        return count

    @abstractmethod
    def search(self, vector: List[float], top_k: int = 5) -> List[SearchResult]:
        """Search for the most similar vectors."""
        ...

    @abstractmethod
    def delete(self, record_id: str) -> bool:
        """Delete a record by ID."""
        ...

    def delete_by_doc(self, doc_id: str) -> int:
        """Delete all records for a document. Returns count deleted."""
        return 0

    @abstractmethod
    def count(self) -> int:
        """Return the number of records in the store."""
        ...

    def clear(self) -> None:
        """Remove all records."""
        pass


class InMemoryVectorStore(VectorStore):
    """
    Simple in-memory vector store with brute-force cosine similarity search.
    Suitable for small to medium collections (<100K vectors).
    """

    def __init__(self) -> None:
        self._records: Dict[str, VectorRecord] = {}

    def add(self, record: VectorRecord) -> None:
        self._records[record.id] = record

    def search(self, vector: List[float], top_k: int = 5) -> List[SearchResult]:
        if not self._records:
            return []

        results: List[Tuple[str, float]] = []
        for rid, record in self._records.items():
            score = self._cosine_similarity(vector, record.vector)
            results.append((rid, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)

        return [
            SearchResult(record=self._records[rid], score=score)
            for rid, score in results[:top_k]
        ]

    def delete(self, record_id: str) -> bool:
        if record_id in self._records:
            del self._records[record_id]
            return True
        return False

    def delete_by_doc(self, doc_id: str) -> int:
        to_delete = [rid for rid, r in self._records.items() if r.doc_id == doc_id]
        for rid in to_delete:
            del self._records[rid]
        return len(to_delete)

    def count(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


class FAISSVectorStore(VectorStore):
    """
    FAISS-backed vector store for high-performance similarity search.
    Requires the `faiss-cpu` or `faiss-gpu` package.
    """

    def __init__(self, dimension: int = 1536) -> None:
        self.dimension = dimension
        self._records: Dict[str, VectorRecord] = {}
        self._id_map: List[str] = []  # Maps FAISS index position to record ID
        self._index = None
        self._init_index()

    def _init_index(self) -> None:
        try:
            import faiss
            self._index = faiss.IndexFlatIP(self.dimension)  # Inner product (for normalized vecs)
            logger.info(f"FAISS index initialized (dim={self.dimension})")
        except ImportError:
            logger.warning("faiss-cpu not installed, falling back to in-memory store")
            self._index = None

    def add(self, record: VectorRecord) -> None:
        self._records[record.id] = record
        self._id_map.append(record.id)

        if self._index is not None:
            import numpy as np
            vec = np.array([record.vector], dtype=np.float32)
            # L2 normalize for cosine similarity via inner product
            faiss.normalize_L2(vec)
            self._index.add(vec)

    def search(self, vector: List[float], top_k: int = 5) -> List[SearchResult]:
        if not self._records:
            return []

        if self._index is None or self._index.ntotal == 0:
            # Fallback to brute force
            return InMemoryVectorStore.search(self, vector, top_k)

        import numpy as np
        import faiss

        query = np.array([vector], dtype=np.float32)
        faiss.normalize_L2(query)

        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(query, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._id_map):
                continue
            rid = self._id_map[idx]
            if rid in self._records:
                results.append(SearchResult(
                    record=self._records[rid],
                    score=float(score),
                ))

        return results

    def delete(self, record_id: str) -> bool:
        if record_id in self._records:
            del self._records[record_id]
            # FAISS doesn't support efficient deletion; rebuild on next search
            # For production, use IndexIDMap
            return True
        return False

    def delete_by_doc(self, doc_id: str) -> int:
        to_delete = [rid for rid, r in self._records.items() if r.doc_id == doc_id]
        for rid in to_delete:
            del self._records[rid]
        return len(to_delete)

    def count(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()
        self._id_map.clear()
        self._init_index()


def get_vector_store(
    backend: str = "auto",
    dimension: int = 1536,
) -> VectorStore:
    """
    Factory function to get a vector store.

    Args:
        backend: "memory", "faiss", or "auto" (tries FAISS first)
        dimension: Vector dimension
    """
    if backend == "memory":
        return InMemoryVectorStore()

    if backend == "faiss" or backend == "auto":
        try:
            store = FAISSVectorStore(dimension=dimension)
            if store._index is not None:
                return store
        except Exception:
            pass

    logger.info("Using in-memory vector store")
    return InMemoryVectorStore()
