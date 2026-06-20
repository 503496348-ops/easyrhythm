"""
Text embedding module (AtomCollide-智械工坊)

Provides text embedding via OpenAI API or a local fallback using
simple TF-IDF-like hashing embeddings.

Supports:
- OpenAI text-embedding-3-small/large
- Local deterministic embeddings (for offline/testing)
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import struct
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TextEmbedder(ABC):
    """Abstract base class for text embedders."""

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """Embed a single text string."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple text strings."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding dimensions."""
        ...


class OpenAIEmbedder(TextEmbedder):
    """
    Text embedder using OpenAI's embedding API.

    Requires OPENAI_API_KEY environment variable.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        dimensions: Optional[int] = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self._dimensions = dimensions or (1536 if "small" in model else 3072)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, text: str) -> List[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        import httpx

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")

        # Truncate overly long texts
        texts = [t[:8191] for t in texts]

        async with httpx.AsyncClient(timeout=60) as client:
            payload: Dict[str, Any] = {
                "input": texts,
                "model": self.model,
            }
            if self._dimensions and "3-" in self.model:
                payload["dimensions"] = self._dimensions

            resp = await client.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            data = resp.json()

            if "data" not in data:
                raise RuntimeError(f"OpenAI embedding error: {data}")

            # Sort by index to maintain order
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in sorted_data]


class LocalEmbedder(TextEmbedder):
    """
    Local deterministic embedder using hash-based feature extraction.
    No external API required. Good for testing and offline use.

    Uses a bag-of-hashes approach: each n-gram is hashed and mapped
    to a position in the embedding vector.
    """

    def __init__(self, dimensions: int = 384, ngram_range: tuple = (2, 4)) -> None:
        self._dimensions = dimensions
        self.ngram_range = ngram_range

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, text: str) -> List[float]:
        return self._compute_embedding(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self._compute_embedding(t) for t in texts]

    def _compute_embedding(self, text: str) -> List[float]:
        """Compute a deterministic embedding from text using hash features."""
        vec = [0.0] * self._dimensions
        text = text.lower().strip()
        if not text:
            return vec

        # Extract character n-grams
        for n in range(self.ngram_range[0], self.ngram_range[1] + 1):
            for i in range(len(text) - n + 1):
                ngram = text[i:i + n]
                # Hash n-gram to position and sign
                h = hashlib.md5(ngram.encode()).digest()
                pos = struct.unpack("<I", h[:4])[0] % self._dimensions
                sign = 1.0 if h[4] & 1 else -1.0
                vec[pos] += sign

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]

        return vec


def get_embedder(
    provider: str = "auto",
    **kwargs,
) -> TextEmbedder:
    """
    Factory function to get the appropriate embedder.

    Args:
        provider: "openai", "local", or "auto" (tries OpenAI first, falls back to local)
        **kwargs: Passed to the embedder constructor
    """
    if provider == "local":
        return LocalEmbedder(**kwargs)

    if provider == "openai" or provider == "auto":
        api_key = kwargs.get("api_key") or os.getenv("OPENAI_API_KEY", "")
        if api_key:
            return OpenAIEmbedder(**kwargs)
        elif provider == "openai":
            raise ValueError("OPENAI_API_KEY required for OpenAI embedder")

    # Auto fallback
    logger.info("No OpenAI API key found, using local embedder")
    return LocalEmbedder(
        dimensions=kwargs.get("dimensions", 384),
    )
