"""Tests for memory tools.

Run with: pytest butler/tools/test_memory.py -v

These tests use mocked database responses - no real PostgreSQL required.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from .embeddings import EMBEDDING_DIM, EmbeddingService
from .memory import (
    DatabasePool,
    RememberFactTool,
    RecallFactsTool,
    GetUserTool,
    GetConversationsTool,
    UpdateSoulTool,
)


FAKE_EMBEDDING = [0.1] * EMBEDDING_DIM


@pytest.fixture
def mock_pool():
    """Create a mock database pool."""
    pool = MagicMock(spec=DatabasePool)
    pool.pool = AsyncMock()
    return pool


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service that returns fake vectors."""
    service = MagicMock(spec=EmbeddingService)
    service.embed = AsyncMock(return_value=FAKE_EMBEDDING)
    return service


class TestDatabasePool:
    """Tests for DatabasePool manager."""

    @pytest.mark.asyncio
    async def test_create_pool(self):
        """Test creating a database pool."""
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = AsyncMock()

            pool = await DatabasePool.create("postgresql://test:test@localhost/db")

            mock_create.assert_called_once()
            assert pool.pool is not None

    @pytest.mark.asyncio
    async def test_create_pool_from_env(self):
        """Test creating pool from environment variable."""
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            with patch.dict("os.environ", {"DATABASE_URL": "postgresql://env:env@localhost/db"}):
                mock_create.return_value = AsyncMock()

                pool = await DatabasePool.create()

                mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_pool_no_url(self):
        """Error when no DATABASE_URL set."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="DATABASE_URL"):
                await DatabasePool.create()

    @pytest.mark.asyncio
    async def test_close_pool(self):
        """Test closing the pool."""
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_asyncpg_pool = AsyncMock()
            mock_create.return_value = mock_asyncpg_pool

            pool = await DatabasePool.create("postgresql://test:test@localhost/db")
            await pool.close()

            mock_asyncpg_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test using pool as context manager."""
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_asyncpg_pool = AsyncMock()
            mock_create.return_value = mock_asyncpg_pool

            async with await DatabasePool.create("postgresql://test:test@localhost/db") as pool:
                assert pool.pool is not None

            mock_asyncpg_pool.close.assert_called_once()


class TestRememberFactTool:
    """Tests for RememberFactTool."""

    def test_tool_properties(self, mock_pool):
        """Verify tool has required properties."""
        tool = RememberFactTool(mock_pool)

        assert tool.name == "remember_fact"
        assert "Store a fact" in tool.description
        assert "user_id" in tool.parameters["properties"]
        assert "fact" in tool.parameters["properties"]
        assert tool.parameters["required"] == ["user_id", "fact"]

    def test_to_schema(self, mock_pool):
        """Verify OpenAI function schema format."""
        tool = RememberFactTool(mock_pool)
        schema = tool.to_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "remember_fact"
        assert "parameters" in schema["function"]

    @pytest.mark.asyncio
    async def test_remember_fact_basic(self, mock_pool):
        """Test storing a basic fact."""
        tool = RememberFactTool(mock_pool)

        result = await tool.execute(
            user_id="user123",
            fact="Prefers dark mode"
        )

        assert "Remembered" in result
        assert "Prefers dark mode" in result

        # Verify database calls
        mock_pool.pool.execute.assert_called()

    @pytest.mark.asyncio
    async def test_remember_fact_with_category(self, mock_pool):
        """Test storing a fact with category."""
        tool = RememberFactTool(mock_pool)

        result = await tool.execute(
            user_id="user123",
            fact="Wakes up at 7am",
            category="schedule",
            confidence=0.8
        )

        assert "Remembered" in result
        assert "Wakes up at 7am" in result

    @pytest.mark.asyncio
    async def test_creates_user_if_not_exists(self, mock_pool):
        """Verify user is created if they don't exist."""
        tool = RememberFactTool(mock_pool)

        await tool.execute(user_id="new_user", fact="Test fact")

        # First call should be the INSERT ... ON CONFLICT for user
        calls = mock_pool.pool.execute.call_args_list
        assert len(calls) >= 2

        # Check first call is user upsert
        first_call_sql = calls[0][0][0]
        assert "butler.users" in first_call_sql
        assert "ON CONFLICT" in first_call_sql


class TestRecallFactsTool:
    """Tests for RecallFactsTool."""

    def test_tool_properties(self, mock_pool):
        """Verify tool has required properties."""
        tool = RecallFactsTool(mock_pool)

        assert tool.name == "recall_facts"
        assert "Recall stored facts" in tool.description
        assert "user_id" in tool.parameters["properties"]
        assert tool.parameters["required"] == ["user_id"]

    @pytest.mark.asyncio
    async def test_recall_no_facts(self, mock_pool):
        """Test when user has no stored facts."""
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        tool = RecallFactsTool(mock_pool)
        result = await tool.execute(user_id="empty_user")

        assert "No facts stored" in result

    @pytest.mark.asyncio
    async def test_recall_facts_grouped(self, mock_pool):
        """Test facts are grouped by category."""
        mock_rows = [
            {"fact": "Likes coffee", "category": "preference", "confidence": 1.0, "created_at": datetime.now(timezone.utc)},
            {"fact": "Works at Acme", "category": "work", "confidence": 0.9, "created_at": datetime.now(timezone.utc)},
            {"fact": "Prefers morning calls", "category": "preference", "confidence": 0.8, "created_at": datetime.now(timezone.utc)},
        ]
        mock_pool.pool.fetch = AsyncMock(return_value=mock_rows)

        tool = RecallFactsTool(mock_pool)
        result = await tool.execute(user_id="user123")

        assert "Known facts about user123" in result
        assert "Preference:" in result
        assert "Likes coffee" in result
        assert "Prefers morning calls" in result
        assert "Work:" in result
        assert "Works at Acme" in result

    @pytest.mark.asyncio
    async def test_recall_with_category_filter(self, mock_pool):
        """Test filtering facts by category."""
        mock_rows = [
            {"fact": "Likes tea", "category": "preference", "confidence": 1.0, "created_at": datetime.now(timezone.utc)},
        ]
        mock_pool.pool.fetch = AsyncMock(return_value=mock_rows)

        tool = RecallFactsTool(mock_pool)
        result = await tool.execute(user_id="user123", category="preference")

        # Verify the query included category filter
        call_args = mock_pool.pool.fetch.call_args
        sql = call_args[0][0]
        assert "category = $2" in sql

    @pytest.mark.asyncio
    async def test_recall_with_limit(self, mock_pool):
        """Test limiting number of facts returned."""
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        tool = RecallFactsTool(mock_pool)
        await tool.execute(user_id="user123", limit=5)

        # Verify limit was passed to query
        call_args = mock_pool.pool.fetch.call_args
        assert 5 in call_args[0]  # limit should be in positional args


class TestGetUserTool:
    """Tests for GetUserTool."""

    def test_tool_properties(self, mock_pool):
        """Verify tool has required properties."""
        tool = GetUserTool(mock_pool)

        assert tool.name == "get_user"
        assert "profile" in tool.description
        assert "user_id" in tool.parameters["properties"]
        assert tool.parameters["required"] == ["user_id"]

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, mock_pool):
        """Test when user doesn't exist."""
        mock_pool.pool.fetchrow = AsyncMock(return_value=None)

        tool = GetUserTool(mock_pool)
        result = await tool.execute(user_id="unknown")

        assert "not found" in result
        assert "unknown" in result

    @pytest.mark.asyncio
    async def test_get_user_basic(self, mock_pool):
        """Test getting a user profile."""
        mock_row = {
            "id": "user123",
            "name": "Alice",
            "soul": None,
            "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        }
        mock_pool.pool.fetchrow = AsyncMock(return_value=mock_row)

        tool = GetUserTool(mock_pool)
        result = await tool.execute(user_id="user123")

        assert "User: Alice" in result
        assert "ID: user123" in result
        assert "2024-01-15" in result

    @pytest.mark.asyncio
    async def test_get_user_with_soul(self, mock_pool):
        """Test getting a user with personality preferences."""
        mock_row = {
            "id": "user123",
            "name": "Bob",
            "soul": {"tone": "friendly", "verbosity": "concise"},
            "created_at": datetime(2024, 6, 1, tzinfo=timezone.utc),
        }
        mock_pool.pool.fetchrow = AsyncMock(return_value=mock_row)

        tool = GetUserTool(mock_pool)
        result = await tool.execute(user_id="user123")

        assert "User: Bob" in result
        assert "Preferences:" in result
        assert "tone: friendly" in result
        assert "verbosity: concise" in result


class TestGetConversationsTool:
    """Tests for GetConversationsTool."""

    def test_tool_properties(self, mock_pool):
        """Verify tool has required properties."""
        tool = GetConversationsTool(mock_pool)

        assert tool.name == "get_conversations"
        assert "conversation history" in tool.description
        assert "user_id" in tool.parameters["properties"]
        assert "days" in tool.parameters["properties"]
        assert "channel" in tool.parameters["properties"]
        assert "limit" in tool.parameters["properties"]
        assert tool.parameters["required"] == ["user_id"]

    def test_to_schema(self, mock_pool):
        """Verify OpenAI function schema format."""
        tool = GetConversationsTool(mock_pool)
        schema = tool.to_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "get_conversations"
        assert "parameters" in schema["function"]

    @pytest.mark.asyncio
    async def test_no_conversations(self, mock_pool):
        """Test when user has no recent conversations."""
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        tool = GetConversationsTool(mock_pool)
        result = await tool.execute(user_id="silent_user")

        assert "No recent conversations" in result
        assert "silent_user" in result

    @pytest.mark.asyncio
    async def test_conversations_grouped_by_date(self, mock_pool):
        """Test conversations are grouped by date in chronological order."""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        mock_rows = [
            # Returned DESC from DB, so newest first
            {"role": "assistant", "content": "The audiobook is great!", "channel": "whatsapp", "created_at": now},
            {"role": "user", "content": "Tell me about the Dune audiobook", "channel": "whatsapp", "created_at": now - timedelta(minutes=1)},
            {"role": "assistant", "content": "Good morning!", "channel": "whatsapp", "created_at": yesterday},
        ]
        mock_pool.pool.fetch = AsyncMock(return_value=mock_rows)

        tool = GetConversationsTool(mock_pool)
        result = await tool.execute(user_id="user123")

        assert "Recent conversations for user123" in result
        assert yesterday.strftime("%Y-%m-%d") in result
        assert now.strftime("%Y-%m-%d") in result
        assert "Dune audiobook" in result

    @pytest.mark.asyncio
    async def test_channel_filter(self, mock_pool):
        """Test filtering by channel passes correct SQL."""
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        tool = GetConversationsTool(mock_pool)
        await tool.execute(user_id="user123", channel="voice")

        call_args = mock_pool.pool.fetch.call_args
        sql = call_args[0][0]
        assert "channel = $2" in sql
        assert call_args[0][1] == "user123"
        assert call_args[0][2] == "voice"

    @pytest.mark.asyncio
    async def test_custom_days_and_limit(self, mock_pool):
        """Test custom days and limit parameters are passed to query."""
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        tool = GetConversationsTool(mock_pool)
        await tool.execute(user_id="user123", days=30, limit=50)

        call_args = mock_pool.pool.fetch.call_args
        assert 30 in call_args[0]  # days
        assert 50 in call_args[0]  # limit

    @pytest.mark.asyncio
    async def test_long_content_truncated(self, mock_pool):
        """Test that long messages are truncated in output."""
        long_content = "A" * 200
        mock_rows = [
            {"role": "user", "content": long_content, "channel": "pwa", "created_at": datetime.now(timezone.utc)},
        ]
        mock_pool.pool.fetch = AsyncMock(return_value=mock_rows)

        tool = GetConversationsTool(mock_pool)
        result = await tool.execute(user_id="user123")

        assert "..." in result
        assert long_content not in result  # full string should not appear

    @pytest.mark.asyncio
    async def test_default_parameters(self, mock_pool):
        """Test default values for days (7) and limit (20)."""
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        tool = GetConversationsTool(mock_pool)
        await tool.execute(user_id="user123")

        call_args = mock_pool.pool.fetch.call_args
        # Without channel: args are (sql, user_id, days, limit)
        assert call_args[0][1] == "user123"
        assert call_args[0][2] == 7    # default days
        assert call_args[0][3] == 20   # default limit


class TestUpdateSoulTool:
    """Tests for UpdateSoulTool."""

    def test_tool_properties(self, mock_pool):
        """Verify tool has required properties."""
        tool = UpdateSoulTool(mock_pool)

        assert tool.name == "update_soul"
        assert "personality" in tool.description
        assert "user_id" in tool.parameters["properties"]
        assert "formality" in tool.parameters["properties"]
        assert "verbosity" in tool.parameters["properties"]
        assert "humor" in tool.parameters["properties"]
        assert "custom_instructions" in tool.parameters["properties"]
        assert tool.parameters["required"] == ["user_id"]

    def test_to_schema(self, mock_pool):
        """Verify OpenAI function schema format."""
        tool = UpdateSoulTool(mock_pool)
        schema = tool.to_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "update_soul"
        assert "parameters" in schema["function"]

    @pytest.mark.asyncio
    async def test_update_single_key(self, mock_pool):
        """Test updating a single soul key."""
        mock_pool.pool.fetchrow = AsyncMock(return_value={
            "soul": {"formality": "casual", "verbosity": "concise"}
        })

        tool = UpdateSoulTool(mock_pool)
        result = await tool.execute(user_id="user123", formality="casual")

        assert "Updated soul for user123" in result
        assert "formality" in result

        # Verify SQL uses jsonb merge
        call_args = mock_pool.pool.fetchrow.call_args
        sql = call_args[0][0]
        assert "||" in sql
        assert "COALESCE" in sql

    @pytest.mark.asyncio
    async def test_update_multiple_keys(self, mock_pool):
        """Test updating multiple soul keys at once."""
        mock_pool.pool.fetchrow = AsyncMock(return_value={
            "soul": {"formality": "formal", "humor": "light", "verbosity": "concise"}
        })

        tool = UpdateSoulTool(mock_pool)
        result = await tool.execute(
            user_id="user123",
            formality="formal",
            humor="light"
        )

        assert "Updated soul for user123" in result

    @pytest.mark.asyncio
    async def test_user_not_found(self, mock_pool):
        """Test updating soul for non-existent user."""
        mock_pool.pool.fetchrow = AsyncMock(return_value=None)

        tool = UpdateSoulTool(mock_pool)
        result = await tool.execute(user_id="ghost", formality="casual")

        assert "not found" in result
        assert "ghost" in result

    @pytest.mark.asyncio
    async def test_no_soul_keys_provided(self, mock_pool):
        """Test error when no soul preferences given."""
        tool = UpdateSoulTool(mock_pool)
        result = await tool.execute(user_id="user123")

        assert "No soul preferences" in result
        # DB should NOT have been called
        mock_pool.pool.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_invalid_keys(self, mock_pool):
        """Test that unknown keys are not passed to the database."""
        tool = UpdateSoulTool(mock_pool)
        result = await tool.execute(user_id="user123", favorite_color="blue")

        assert "No soul preferences" in result

    @pytest.mark.asyncio
    async def test_custom_instructions(self, mock_pool):
        """Test setting custom_instructions."""
        mock_pool.pool.fetchrow = AsyncMock(return_value={
            "soul": {"custom_instructions": "Always greet me in Spanish"}
        })

        tool = UpdateSoulTool(mock_pool)
        result = await tool.execute(
            user_id="user123",
            custom_instructions="Always greet me in Spanish"
        )

        assert "Updated soul for user123" in result
        assert "custom_instructions" in result

    @pytest.mark.asyncio
    async def test_displays_full_soul_after_update(self, mock_pool):
        """Test that response shows the complete merged soul config."""
        mock_pool.pool.fetchrow = AsyncMock(return_value={
            "soul": {
                "personality": "warm",
                "formality": "casual",
                "verbosity": "concise",
            }
        })

        tool = UpdateSoulTool(mock_pool)
        result = await tool.execute(user_id="user123", formality="casual")

        # Should show ALL soul keys, not just the updated one
        assert "personality: warm" in result
        assert "formality: casual" in result
        assert "verbosity: concise" in result


class TestRememberFactWithEmbeddings:
    """Tests for RememberFactTool with embedding service."""

    @pytest.mark.asyncio
    async def test_stores_embedding_when_service_available(self, mock_pool, mock_embedding_service):
        """Test that embedding is generated and stored alongside the fact."""
        tool = RememberFactTool(mock_pool, mock_embedding_service)

        result = await tool.execute(user_id="user123", fact="Likes spicy Thai food")

        assert "Remembered" in result

        # Verify embedding was requested
        mock_embedding_service.embed.assert_called_once_with("Likes spicy Thai food")

        # Verify INSERT includes embedding (the vector cast)
        calls = mock_pool.pool.execute.call_args_list
        fact_insert_sql = calls[-1][0][0]
        assert "embedding" in fact_insert_sql
        assert "::vector" in fact_insert_sql

    @pytest.mark.asyncio
    async def test_stores_without_embedding_on_failure(self, mock_pool):
        """Test graceful fallback when embedding service returns None."""
        failing_service = MagicMock(spec=EmbeddingService)
        failing_service.embed = AsyncMock(return_value=None)

        tool = RememberFactTool(mock_pool, failing_service)

        result = await tool.execute(user_id="user123", fact="Test fact")

        assert "Remembered" in result

        # Verify INSERT does NOT include embedding column
        calls = mock_pool.pool.execute.call_args_list
        fact_insert_sql = calls[-1][0][0]
        assert "embedding" not in fact_insert_sql

    @pytest.mark.asyncio
    async def test_stores_without_embedding_when_no_service(self, mock_pool):
        """Test that tool works normally without embedding service (backward compat)."""
        tool = RememberFactTool(mock_pool)  # No embedding_service

        result = await tool.execute(user_id="user123", fact="Test fact")

        assert "Remembered" in result

        # Verify INSERT does NOT include embedding column
        calls = mock_pool.pool.execute.call_args_list
        fact_insert_sql = calls[-1][0][0]
        assert "embedding" not in fact_insert_sql


class TestRecallFactsWithSemanticSearch:
    """Tests for RecallFactsTool semantic search functionality."""

    def test_query_parameter_in_schema(self, mock_pool):
        """Verify the query parameter is exposed in the tool schema."""
        tool = RecallFactsTool(mock_pool)
        assert "query" in tool.parameters["properties"]
        assert "semantic" in tool.parameters["properties"]["query"]["description"].lower()

    @pytest.mark.asyncio
    async def test_semantic_search_with_query(self, mock_pool, mock_embedding_service):
        """Test semantic search when query is provided."""
        mock_rows = [
            {"fact": "Likes spicy Thai food", "category": "preference", "confidence": 1.0, "distance": 0.15},
            {"fact": "Allergic to peanuts", "category": "health", "confidence": 0.9, "distance": 0.35},
        ]
        mock_pool.pool.fetch = AsyncMock(return_value=mock_rows)

        tool = RecallFactsTool(mock_pool, mock_embedding_service)
        result = await tool.execute(user_id="user123", query="food preferences")

        # Verify embedding was generated for the query
        mock_embedding_service.embed.assert_called_once_with("food preferences")

        # Verify vector similarity SQL was used
        call_args = mock_pool.pool.fetch.call_args
        sql = call_args[0][0]
        assert "<=>" in sql
        assert "::vector" in sql

        # Verify output contains facts with relevance scores
        assert "Likes spicy Thai food" in result
        assert "Allergic to peanuts" in result
        assert "relevance:" in result

    @pytest.mark.asyncio
    async def test_semantic_search_with_category(self, mock_pool, mock_embedding_service):
        """Test semantic search filtered by category."""
        mock_rows = [
            {"fact": "Likes pasta", "category": "preference", "confidence": 1.0, "distance": 0.2},
        ]
        mock_pool.pool.fetch = AsyncMock(return_value=mock_rows)

        tool = RecallFactsTool(mock_pool, mock_embedding_service)
        result = await tool.execute(user_id="user123", query="food", category="preference")

        # Verify SQL includes both category filter and vector search
        call_args = mock_pool.pool.fetch.call_args
        sql = call_args[0][0]
        assert "category = $2" in sql
        assert "<=>" in sql

    @pytest.mark.asyncio
    async def test_falls_back_when_embedding_fails(self, mock_pool):
        """Test fallback to category search when embedding generation fails."""
        failing_service = MagicMock(spec=EmbeddingService)
        failing_service.embed = AsyncMock(return_value=None)

        mock_rows = [
            {"fact": "Likes coffee", "category": "preference", "confidence": 1.0, "created_at": datetime.now(timezone.utc)},
        ]
        mock_pool.pool.fetch = AsyncMock(return_value=mock_rows)

        tool = RecallFactsTool(mock_pool, failing_service)
        result = await tool.execute(user_id="user123", query="drinks")

        # Should fall back to category-based search (no <=> in SQL)
        call_args = mock_pool.pool.fetch.call_args
        sql = call_args[0][0]
        assert "<=>" not in sql

        # Should still return facts in category format
        assert "Known facts about user123" in result

    @pytest.mark.asyncio
    async def test_falls_back_when_no_service(self, mock_pool):
        """Test that query is ignored when no embedding service is configured."""
        mock_rows = [
            {"fact": "Likes coffee", "category": "preference", "confidence": 1.0, "created_at": datetime.now(timezone.utc)},
        ]
        mock_pool.pool.fetch = AsyncMock(return_value=mock_rows)

        tool = RecallFactsTool(mock_pool)  # No embedding_service
        result = await tool.execute(user_id="user123", query="food preferences")

        # Should use category-based search
        call_args = mock_pool.pool.fetch.call_args
        sql = call_args[0][0]
        assert "<=>" not in sql

        assert "Known facts about user123" in result

    @pytest.mark.asyncio
    async def test_semantic_search_no_results(self, mock_pool, mock_embedding_service):
        """Test semantic search with no matching facts."""
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        tool = RecallFactsTool(mock_pool, mock_embedding_service)
        result = await tool.execute(user_id="user123", query="quantum physics")

        assert "No matching facts" in result

    @pytest.mark.asyncio
    async def test_category_search_unchanged(self, mock_pool):
        """Test that category-based search is completely unchanged."""
        mock_rows = [
            {"fact": "Works at Acme", "category": "work", "confidence": 1.0, "created_at": datetime.now(timezone.utc)},
        ]
        mock_pool.pool.fetch = AsyncMock(return_value=mock_rows)

        tool = RecallFactsTool(mock_pool)
        result = await tool.execute(user_id="user123", category="work")

        # Verify original SQL is used
        call_args = mock_pool.pool.fetch.call_args
        sql = call_args[0][0]
        assert "category = $2" in sql
        assert "<=>" not in sql
        assert "ORDER BY confidence DESC" in sql

        assert "Works at Acme" in result


class TestToolCleanup:
    """Tests for tool resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_owned_pool(self):
        """Test that tools clean up their own pools."""
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://test@localhost/db"}):
            with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
                mock_asyncpg_pool = AsyncMock()
                mock_create.return_value = mock_asyncpg_pool

                # Create tool without shared pool (will create its own)
                tool = RememberFactTool()

                # Trigger lazy pool creation
                await tool._get_pool()

                # Close the tool
                await tool.close()

                # Verify pool was closed
                mock_asyncpg_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_close_shared_pool(self, mock_pool):
        """Test that tools don't close shared pools."""
        tool = RememberFactTool(mock_pool)

        await tool.close()

        # Shared pool should not be closed by tool
        mock_pool.pool.close.assert_not_called()


class TestEmbeddingRoundTrip:
    """Integration test: embed → store → search round-trip."""

    @pytest.mark.asyncio
    async def test_embed_store_search_round_trip(self, mock_pool, mock_embedding_service):
        """Verify a fact can be embedded, stored, and found via semantic search."""
        # 1. Store a fact with embedding
        remember = RememberFactTool(mock_pool, mock_embedding_service)
        result = await remember.execute(
            user_id="user123", fact="Loves hiking in the mountains"
        )
        assert "Remembered" in result
        mock_embedding_service.embed.assert_called_with("Loves hiking in the mountains")

        # Verify the stored vector is the right size
        store_call = mock_pool.pool.execute.call_args_list[-1]
        stored_vector_str = store_call[0][-1]  # last positional arg is the vector string
        stored_dims = stored_vector_str.count(",") + 1
        assert stored_dims == EMBEDDING_DIM

        # 2. Search for the fact semantically
        mock_pool.pool.fetch = AsyncMock(return_value=[
            {"fact": "Loves hiking in the mountains", "category": "preference",
             "confidence": 1.0, "distance": 0.05},
        ])
        mock_embedding_service.embed.reset_mock()

        recall = RecallFactsTool(mock_pool, mock_embedding_service)
        result = await recall.execute(user_id="user123", query="outdoor activities")

        # Query was embedded
        mock_embedding_service.embed.assert_called_once_with("outdoor activities")

        # Vector similarity SQL was used
        search_sql = mock_pool.pool.fetch.call_args[0][0]
        assert "<=>" in search_sql

        # Result contains the stored fact with high relevance
        assert "Loves hiking in the mountains" in result
        assert "relevance: 95%" in result

    @pytest.mark.asyncio
    async def test_wrong_dimension_embedding_not_stored(self, mock_pool):
        """Verify that a wrong-dimension embedding is discarded before DB insert."""
        wrong_dim_service = MagicMock(spec=EmbeddingService)
        wrong_dim_service.embed = AsyncMock(return_value=[0.1] * 1536)  # wrong dims

        tool = RememberFactTool(mock_pool, wrong_dim_service)
        result = await tool.execute(user_id="user123", fact="Test fact")

        assert "Remembered" in result

        # Verify INSERT does NOT include embedding (fell back to fact-only)
        calls = mock_pool.pool.execute.call_args_list
        fact_insert_sql = calls[-1][0][0]
        assert "embedding" not in fact_insert_sql


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
