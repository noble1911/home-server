"""Embedding service for semantic vector search.

Calls Ollama's embedding API to generate vector representations of text,
enabling semantic similarity search across stored facts.

Usage:
    service = EmbeddingService("http://ollama:11434")
    vector = await service.embed("Likes spicy Thai food")
    # Returns list of 768 floats, or None on failure
"""

from __future__ import annotations

import logging

import aiohttp

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate text embeddings via Ollama's local API.

    Uses nomic-embed-text (768 dimensions) by default. Returns None on any
    failure so callers can gracefully degrade to non-vector behaviour.
    """

    def __init__(
        self,
        ollama_url: str = "http://ollama:11434",
        model: str = "nomic-embed-text",
    ):
        self._url = ollama_url.rstrip("/")
        self._model = model

    async def embed(self, text: str) -> list[float] | None:
        """Generate an embedding vector for the given text.

        Args:
            text: The text to embed.

        Returns:
            List of floats (768-dim for nomic-embed-text), or None on error.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._url}/api/embed",
                    json={"model": self._model, "input": text},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Ollama embedding failed: %d %s",
                            resp.status,
                            await resp.text(),
                        )
                        return None
                    data = await resp.json()
                    embeddings = data.get("embeddings")
                    if not embeddings or not embeddings[0]:
                        logger.warning("Ollama returned empty embeddings")
                        return None
                    return embeddings[0]
        except (aiohttp.ClientError, TimeoutError, Exception) as exc:
            logger.warning("Embedding request failed: %s", exc)
            return None
