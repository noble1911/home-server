"""Tests for context loading and multi-turn conversation history.

Run with: pytest butler/api/test_context.py -v

These tests use mocked database responses - no real PostgreSQL required.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from .context import (
    UserContext,
    _build_system_blocks,
    _load_facts,
    _hybrid_fact_search,
    load_user_context,
    load_conversation_messages,
)
from .llm import _build_messages


def _blocks_text(blocks: list[dict]) -> str:
    """Join all text blocks into a single string for assertion convenience."""
    return "\n".join(b["text"] for b in blocks if b.get("type") == "text")


@pytest.fixture
def mock_pool():
    """Create a mock database pool matching tools.DatabasePool interface."""
    pool = MagicMock()
    pool.pool = AsyncMock()
    return pool


def _make_history_row(role, content, minutes_ago=0):
    """Helper to create a conversation history row dict."""
    return {"role": role, "content": content}


class TestBuildSystemBlocks:
    """Tests for _build_system_blocks (personality + facts only, no history)."""

    def test_basic_prompt_structure(self):
        """System prompt contains role and user name."""
        blocks = _build_system_blocks("Ron", {}, [])
        text = _blocks_text(blocks)

        assert "Butler" in text
        assert "Ron" in text

    def test_returns_list_of_blocks(self):
        """System prompt is a list of content blocks with cache_control."""
        blocks = _build_system_blocks("Ron", {}, [])

        assert isinstance(blocks, list)
        assert len(blocks) >= 2
        # First block (RULES) should have cache_control
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}
        # Last block (dynamic content) should NOT have cache_control
        assert "cache_control" not in blocks[-1]

    def test_no_history_in_prompt(self):
        """System prompt no longer contains conversation history."""
        text = _blocks_text(_build_system_blocks("Ron", {}, []))

        assert "RECENT CONTEXT" not in text

    def test_personality_included(self):
        """Soul config personality fields appear in prompt."""
        soul = {"personality": "friendly", "humor": "dry wit"}
        text = _blocks_text(_build_system_blocks("Ron", soul, []))

        assert "friendly" in text
        assert "dry wit" in text

    def test_facts_included(self):
        """Known facts appear in prompt."""
        facts = [
            {"fact": "Loves Italian food", "category": "preference"},
            {"fact": "Has a cat named Luna", "category": "other"},
        ]
        text = _blocks_text(_build_system_blocks("Ron", {}, facts))

        assert "Loves Italian food" in text
        assert "Has a cat named Luna" in text
        assert "[preference]" in text

    def test_rules_included(self):
        """Behavioral rules appear in prompt."""
        text = _blocks_text(_build_system_blocks("Ron", {}, []))

        assert "RULES:" in text
        assert "remember_fact" in text

    def test_custom_butler_name(self):
        """Soul config can override butler name."""
        soul = {"butler_name": "Jarvis"}
        text = _blocks_text(_build_system_blocks("Ron", soul, []))

        assert "Jarvis" in text


class TestLoadConversationMessages:
    """Tests for load_conversation_messages."""

    @pytest.mark.asyncio
    async def test_returns_chronological_messages(self, mock_pool):
        """Messages returned in chronological order (oldest first)."""
        # DB returns DESC (newest first)
        mock_pool.pool.fetch = AsyncMock(return_value=[
            {"role": "assistant", "content": "It's sunny!"},
            {"role": "user", "content": "What's the weather?"},
        ])

        with patch("api.context.settings") as mock_settings:
            mock_settings.max_history_messages = 20
            messages = await load_conversation_messages(mock_pool, "user1")

        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "What's the weather?"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "It's sunny!"

    @pytest.mark.asyncio
    async def test_merges_consecutive_same_role(self, mock_pool):
        """Consecutive same-role messages are merged."""
        mock_pool.pool.fetch = AsyncMock(return_value=[
            {"role": "user", "content": "Second part"},
            {"role": "user", "content": "First part"},
        ])

        with patch("api.context.settings") as mock_settings:
            mock_settings.max_history_messages = 20
            messages = await load_conversation_messages(mock_pool, "user1")

        assert len(messages) == 1
        assert "First part" in messages[0]["content"]
        assert "Second part" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_empty_history(self, mock_pool):
        """No messages returns empty list."""
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        with patch("api.context.settings") as mock_settings:
            mock_settings.max_history_messages = 20
            messages = await load_conversation_messages(mock_pool, "user1")

        assert messages == []

    @pytest.mark.asyncio
    async def test_uses_configured_limit(self, mock_pool):
        """Respects max_history_messages setting."""
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        with patch("api.context.settings") as mock_settings:
            mock_settings.max_history_messages = 10
            await load_conversation_messages(mock_pool, "user1")

        call_args = mock_pool.pool.fetch.call_args
        # The limit parameter should be 10
        assert call_args[0][2] == 10


class TestLoadUserContext:
    """Tests for load_user_context database interactions."""

    @pytest.mark.asyncio
    async def test_unknown_user_returns_defaults(self, mock_pool):
        """When user not found, return default context."""
        mock_pool.pool.fetchrow = AsyncMock(return_value=None)

        ctx = await load_user_context(mock_pool, "unknown")

        assert isinstance(ctx, UserContext)
        assert ctx.user_name == "User"
        assert ctx.butler_name == "Butler"
        assert "Butler" in _blocks_text(ctx.system_prompt)
        assert ctx.history == []

    @pytest.mark.asyncio
    async def test_context_includes_history(self, mock_pool):
        """UserContext.history is populated with conversation messages."""
        mock_pool.pool.fetchrow = AsyncMock(return_value={
            "id": "user1", "name": "Ron", "soul": {},
        })

        history_rows = [
            {"role": "assistant", "content": "It's 22 degrees"},
            {"role": "user", "content": "What's the temp?"},
        ]

        # First fetch = facts, second fetch = history
        mock_pool.pool.fetch = AsyncMock(side_effect=[[], history_rows])

        with patch("api.context.settings") as mock_settings:
            mock_settings.max_history_messages = 20
            ctx = await load_user_context(mock_pool, "user1")

        assert len(ctx.history) == 2
        assert ctx.history[0]["role"] == "user"
        assert ctx.history[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_history_not_in_system_prompt(self, mock_pool):
        """Conversation history should NOT appear in system prompt."""
        mock_pool.pool.fetchrow = AsyncMock(return_value={
            "id": "user1", "name": "Ron", "soul": {},
        })

        history_rows = [
            {"role": "user", "content": "What's the temp?"},
        ]

        mock_pool.pool.fetch = AsyncMock(side_effect=[[], history_rows])

        with patch("api.context.settings") as mock_settings:
            mock_settings.max_history_messages = 20
            ctx = await load_user_context(mock_pool, "user1")

        # History content should NOT be in system prompt (it's in messages now)
        assert "What's the temp?" not in _blocks_text(ctx.system_prompt)


class TestLoadFacts:
    """Tests for _load_facts with semantic and confidence fallback."""

    @pytest.mark.asyncio
    async def test_fallback_without_embedding_service(self):
        """Without embedding_service, falls back to confidence-based query."""
        db = AsyncMock()
        db.fetch = AsyncMock(return_value=[
            {"fact": "Likes coffee", "category": "preference"},
        ])

        facts = await _load_facts(db, "user1", current_message="hello")
        assert len(facts) == 1
        assert facts[0]["fact"] == "Likes coffee"

    @pytest.mark.asyncio
    async def test_fallback_without_message(self):
        """Without current_message, falls back to confidence-based query."""
        db = AsyncMock()
        db.fetch = AsyncMock(return_value=[])
        embedding_svc = AsyncMock()

        facts = await _load_facts(db, "user1", embedding_service=embedding_svc)
        assert facts == []
        # embed() should NOT have been called
        embedding_svc.embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_semantic_path_when_both_provided(self):
        """With message + embedding_service, uses hybrid search."""
        db = AsyncMock()
        embedding_svc = AsyncMock()
        embedding_svc.embed = AsyncMock(return_value=[0.1] * 768)

        # _hybrid_fact_search will be called, mock the two db.fetch calls
        db.fetch = AsyncMock(side_effect=[
            [{"id": 1, "fact": "Semantic fact", "category": "general"}],
            [{"id": 2, "fact": "Confidence fact", "category": "general"}],
        ])

        facts = await _load_facts(
            db, "user1",
            current_message="dinner plans",
            embedding_service=embedding_svc,
        )
        embedding_svc.embed.assert_called_once_with("dinner plans")
        assert len(facts) == 2

    @pytest.mark.asyncio
    async def test_semantic_fallback_on_embed_failure(self):
        """If embed() returns None, falls back to confidence-based query."""
        db = AsyncMock()
        embedding_svc = AsyncMock()
        embedding_svc.embed = AsyncMock(return_value=None)

        db.fetch = AsyncMock(return_value=[
            {"fact": "Fallback fact", "category": "general"},
        ])

        facts = await _load_facts(
            db, "user1",
            current_message="hello",
            embedding_service=embedding_svc,
        )
        # Should fall back to single confidence query
        assert len(facts) == 1
        assert facts[0]["fact"] == "Fallback fact"


class TestHybridFactSearch:
    """Tests for _hybrid_fact_search deduplication logic."""

    @pytest.mark.asyncio
    async def test_deduplication(self):
        """Facts appearing in both semantic and confidence results are deduplicated."""
        db = AsyncMock()
        db.fetch = AsyncMock(side_effect=[
            # Semantic results
            [
                {"id": 1, "fact": "Likes Italian", "category": "food"},
                {"id": 2, "fact": "Has a cat", "category": "pets"},
            ],
            # Confidence results (id=1 overlaps)
            [
                {"id": 1, "fact": "Likes Italian", "category": "food"},
                {"id": 3, "fact": "Works remotely", "category": "work"},
            ],
        ])

        facts = await _hybrid_fact_search(db, "user1", [0.1] * 768)
        assert len(facts) == 3
        fact_ids = [f["id"] for f in facts]
        assert fact_ids == [1, 2, 3]  # Semantic first, then unique confidence

    @pytest.mark.asyncio
    async def test_semantic_priority(self):
        """Semantic results come before confidence-only results."""
        db = AsyncMock()
        db.fetch = AsyncMock(side_effect=[
            [{"id": 10, "fact": "Relevant to query", "category": "general"}],
            [{"id": 20, "fact": "High confidence", "category": "general"}],
        ])

        facts = await _hybrid_fact_search(db, "user1", [0.5] * 768)
        assert facts[0]["id"] == 10
        assert facts[1]["id"] == 20


class TestBuildMessages:
    """Tests for _build_messages in llm.py."""

    def test_no_history(self):
        """Without history, returns a single user message."""
        messages = _build_messages("Hello")
        assert messages == [{"role": "user", "content": "Hello"}]

    def test_with_normal_history(self):
        """History + current message produces correct messages array."""
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        messages = _build_messages("How are you?", history)
        assert len(messages) == 3
        assert messages[0] == {"role": "user", "content": "Hi"}
        assert messages[1] == {"role": "assistant", "content": "Hello!"}
        assert messages[2] == {"role": "user", "content": "How are you?"}

    def test_strips_leading_assistant_messages(self):
        """Leading assistant messages are dropped (Claude API requires user first)."""
        history = [
            {"role": "assistant", "content": "Orphaned reply"},
            {"role": "user", "content": "Real question"},
            {"role": "assistant", "content": "Real answer"},
        ]
        messages = _build_messages("Follow-up", history)
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Real question"
        assert len(messages) == 3

    def test_strips_multiple_leading_assistant_messages(self):
        """Multiple leading assistant messages are all dropped."""
        history = [
            {"role": "assistant", "content": "First orphan"},
            {"role": "assistant", "content": "Second orphan"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        messages = _build_messages("World", history)
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert len(messages) == 3

    def test_all_assistant_history_stripped(self):
        """If history is all assistant messages, only current message remains."""
        history = [
            {"role": "assistant", "content": "Orphan 1"},
            {"role": "assistant", "content": "Orphan 2"},
        ]
        messages = _build_messages("Hello")
        assert messages == [{"role": "user", "content": "Hello"}]

    def test_merges_trailing_user_in_history(self):
        """If history ends with user, current message is merged to avoid consecutive user roles."""
        history = [
            {"role": "user", "content": "Previous unanswered question"},
        ]
        messages = _build_messages("New question", history)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "Previous unanswered question" in messages[0]["content"]
        assert "New question" in messages[0]["content"]
