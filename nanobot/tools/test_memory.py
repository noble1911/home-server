"""Tests for memory tools.

Run with: pytest nanobot/tools/test_memory.py -v

These tests use mocked database responses - no real PostgreSQL required.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from .memory import DatabasePool, RememberFactTool, RecallFactsTool, GetUserTool


@pytest.fixture
def mock_pool():
    """Create a mock database pool."""
    pool = MagicMock(spec=DatabasePool)
    pool.pool = AsyncMock()
    return pool


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


class TestToolCleanup:
    """Tests for tool resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_owned_pool(self):
        """Test that tools clean up their own pools."""
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
