"""
EasyRhythm Knowledge Base + RAG (AtomCollide-智械工坊)

Provides a self-contained RAG (Retrieval-Augmented Generation) system
inspired by Dify's knowledge base pattern:

- Document loading from files and URLs
- Text embedding via OpenAI or local fallback
- Vector store with in-memory and FAISS backends
- Top-k retrieval with context injection

Agents can use the knowledge base to ground their responses in
domain-specific documents.
"""

from .store import VectorStore, InMemoryVectorStore, FAISSVectorStore
from .embedder import TextEmbedder, OpenAIEmbedder, LocalEmbedder
from .retriever import RAGRetriever
from .loader import DocumentLoader, Document

__all__ = [
    "VectorStore",
    "InMemoryVectorStore",
    "FAISSVectorStore",
    "TextEmbedder",
    "OpenAIEmbedder",
    "LocalEmbedder",
    "RAGRetriever",
    "DocumentLoader",
    "Document",
]
