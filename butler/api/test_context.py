"""Tests for cross-channel context loading.

Run with: pytest butler/api/test_context.py -v

These tests use mocked database responses - no real PostgreSQL required.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from .context import UserContext, _build_system_prompt, _channel_label, load_user_context


@pytest.fixture
def mock_pool():
    """Create a mock database pool matching tools.DatabasePool interface."""
    pool = MagicMock()
    pool.pool = AsyncMock()
    return pool


def _make_history_row(role, content, channel, minutes_ago=0):
    """Helper to create a conversation history row dict."""
    ts = datetime(2026, 2, 5, 12, 0, 0, tzinfo=timezone.utc) - timedelta(minutes=minutes_ago)
    return {"role": role, "content": content, "channel": channel, "created_at": ts}


class TestChannelLabel:
    """Tests for _channel_label helper."""

    def test_voice_channel(self):
        assert _channel_label("voice") == "[via voice]"

    def test_pwa_channel(self):
        assert _channel_label("pwa") == "[via text]"

    def test_whatsapp_channel(self):
        assert _channel_label("whatsapp") == "[via whatsapp]"

    def test_telegram_channel(self):
        assert _channel_label("telegram") == "[via telegram]"

    def test_unknown_channel_fallback(self):
        assert _channel_label("sms") == "[via sms]"


class TestBuildSystemPrompt:
    """Tests for _build_system_prompt with channel indicators."""

    def test_cross_channel_history_includes_labels(self):
        """Messages from different channels get correct labels."""
        history = [
            _make_history_row("user", "What's the weather?", "voice", minutes_ago=10),
            _make_history_row("assistant", "It's sunny and 20C.", "voice", minutes_ago=9),
            _make_history_row("user", "Tell me more", "pwa", minutes_ago=5),
            _make_history_row("assistant", "UV index is high today.", "pwa", minutes_ago=4),
        ]
        prompt = _build_system_prompt("Ron", {}, [], history)

        assert "[via voice]" in prompt
        assert "[via text]" in prompt
        assert "What's the weather?" in prompt
        assert "Tell me more" in prompt

    def test_history_shown_chronologically(self):
        """Messages should appear oldest-first in the prompt (DB returns newest-first)."""
        history = [
            # DB returns DESC (newest first)
            _make_history_row("user", "Second message", "pwa", minutes_ago=0),
            _make_history_row("user", "First message", "voice", minutes_ago=10),
        ]
        prompt = _build_system_prompt("Ron", {}, [], history)

        first_pos = prompt.index("First message")
        second_pos = prompt.index("Second message")
        assert first_pos < second_pos

    def test_whatsapp_channel_in_history(self):
        """WhatsApp messages get proper labels."""
        history = [
            _make_history_row("user", "Hi from WhatsApp", "whatsapp"),
        ]
        prompt = _build_system_prompt("Ron", {}, [], history)

        assert "[via whatsapp]" in prompt
        assert "Hi from WhatsApp" in prompt

    def test_empty_history_no_context_section(self):
        """No RECENT CONTEXT section when history is empty."""
        prompt = _build_system_prompt("Ron", {}, [], [])

        assert "RECENT CONTEXT" not in prompt

    def test_content_truncated_at_100_chars(self):
        """Long messages should be truncated in the prompt."""
        long_msg = "A" * 200
        history = [_make_history_row("user", long_msg, "pwa")]
        prompt = _build_system_prompt("Ron", {}, [], history)

        # The full 200-char message should not appear
        assert long_msg not in prompt
        # But the first 100 chars should
        assert "A" * 100 in prompt

    def test_header_mentions_all_channels(self):
        """The context section header should indicate cross-channel scope."""
        history = [_make_history_row("user", "Hello", "voice")]
        prompt = _build_system_prompt("Ron", {}, [], history)

        assert "across all channels" in prompt

    def test_missing_channel_defaults_to_pwa(self):
        """Rows with no channel key default to [via text]."""
        row = {"role": "user", "content": "Old message", "created_at": datetime.now(timezone.utc)}
        prompt = _build_system_prompt("Ron", {}, [], [row])

        assert "[via text]" in prompt


class TestLoadUserContext:
    """Tests for load_user_context database interactions."""

    @pytest.mark.asyncio
    async def test_loads_history_across_channels(self, mock_pool):
        """Verify the SQL does NOT filter by channel."""
        mock_pool.pool.fetchrow = AsyncMock(return_value={
            "id": "user1", "name": "Ron", "soul": {},
        })
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        await load_user_context(mock_pool, "user1")

        # The conversation history query is the second db.fetch call
        history_call = mock_pool.pool.fetch.call_args_list[1]
        sql = history_call[0][0]

        # Must NOT contain channel filter
        assert "channel =" not in sql.lower()
        # Must SELECT channel column
        assert "channel" in sql.lower()

    @pytest.mark.asyncio
    async def test_history_limit_is_20(self, mock_pool):
        """Verify the query fetches up to 20 messages."""
        mock_pool.pool.fetchrow = AsyncMock(return_value={
            "id": "user1", "name": "Ron", "soul": {},
        })
        mock_pool.pool.fetch = AsyncMock(return_value=[])

        await load_user_context(mock_pool, "user1")

        history_call = mock_pool.pool.fetch.call_args_list[1]
        sql = history_call[0][0]

        assert "LIMIT 20" in sql

    @pytest.mark.asyncio
    async def test_unknown_user_returns_defaults(self, mock_pool):
        """When user not found, return default context."""
        mock_pool.pool.fetchrow = AsyncMock(return_value=None)

        ctx = await load_user_context(mock_pool, "unknown")

        assert isinstance(ctx, UserContext)
        assert ctx.user_name == "User"
        assert ctx.butler_name == "Butler"
        assert "Butler" in ctx.system_prompt

    @pytest.mark.asyncio
    async def test_cross_channel_messages_in_prompt(self, mock_pool):
        """End-to-end: voice + text messages both appear in system prompt."""
        mock_pool.pool.fetchrow = AsyncMock(return_value={
            "id": "user1", "name": "Ron", "soul": {},
        })

        history_rows = [
            _make_history_row("user", "Check the lights", "pwa", minutes_ago=0),
            _make_history_row("assistant", "Lights are on", "pwa", minutes_ago=1),
            _make_history_row("user", "What's the temp?", "voice", minutes_ago=5),
            _make_history_row("assistant", "It's 22 degrees", "voice", minutes_ago=4),
        ]

        # First fetch = facts, second fetch = history
        mock_pool.pool.fetch = AsyncMock(side_effect=[[], history_rows])

        ctx = await load_user_context(mock_pool, "user1")

        assert "[via voice]" in ctx.system_prompt
        assert "[via text]" in ctx.system_prompt
        assert "What's the temp?" in ctx.system_prompt
        assert "Check the lights" in ctx.system_prompt
