"""Tests for the embedding service.

Run with: pytest butler/tools/test_embeddings.py -v

These tests use mocked HTTP responses - no real Ollama server required.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from .embeddings import EMBEDDING_DIM, EmbeddingService


FAKE_EMBEDDING = [0.1] * EMBEDDING_DIM


class TestEmbeddingService:
    """Tests for EmbeddingService."""

    def test_default_config(self):
        """Verify default Ollama URL and model."""
        service = EmbeddingService()
        assert service._url == "http://ollama:11434"
        assert service._model == "nomic-embed-text"

    def test_custom_config(self):
        """Verify custom URL and model."""
        service = EmbeddingService("http://localhost:11434/", "mxbai-embed-large")
        assert service._url == "http://localhost:11434"  # trailing slash stripped
        assert service._model == "mxbai-embed-large"

    @pytest.mark.asyncio
    async def test_embed_success(self):
        """Test successful embedding generation."""
        service = EmbeddingService("http://ollama:11434")

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"embeddings": [FAKE_EMBEDDING]})

        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_ctx)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_ctx):
            result = await service.embed("test text")

        assert result == FAKE_EMBEDDING

    @pytest.mark.asyncio
    async def test_embed_http_error(self):
        """Test graceful handling of non-200 response."""
        service = EmbeddingService("http://ollama:11434")

        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="Internal Server Error")

        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_ctx)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_ctx):
            result = await service.embed("test text")

        assert result is None

    @pytest.mark.asyncio
    async def test_embed_empty_response(self):
        """Test graceful handling of empty embeddings."""
        service = EmbeddingService("http://ollama:11434")

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"embeddings": []})

        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_ctx)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_ctx):
            result = await service.embed("test text")

        assert result is None

    @pytest.mark.asyncio
    async def test_embed_dimension_mismatch(self):
        """Test that wrong-dimension vectors are rejected."""
        service = EmbeddingService("http://ollama:11434")

        wrong_dim_embedding = [0.1] * 1536  # OpenAI ada-002 size, not ours

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"embeddings": [wrong_dim_embedding]})

        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_ctx)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_ctx):
            result = await service.embed("test text")

        assert result is None

    @pytest.mark.asyncio
    async def test_embed_connection_error(self):
        """Test graceful handling when Ollama is unreachable."""
        service = EmbeddingService("http://ollama:11434")

        with patch("aiohttp.ClientSession") as mock_cls:
            mock_session_ctx = AsyncMock()
            mock_session_ctx.__aenter__ = AsyncMock(
                side_effect=aiohttp.ClientConnectorError(
                    connection_key=MagicMock(), os_error=OSError("Connection refused")
                )
            )
            mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_session_ctx

            result = await service.embed("test text")

        assert result is None

    @pytest.mark.asyncio
    async def test_embed_timeout(self):
        """Test graceful handling of request timeout."""
        service = EmbeddingService("http://ollama:11434")

        with patch("aiohttp.ClientSession") as mock_cls:
            mock_session_ctx = AsyncMock()
            mock_session_ctx.__aenter__ = AsyncMock(side_effect=TimeoutError())
            mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_session_ctx

            result = await service.embed("test text")

        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
