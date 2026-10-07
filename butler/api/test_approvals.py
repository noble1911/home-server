"""Tests for tap-to-approve pending actions (no DB, no network).

Run with: pytest butler/api/test_approvals.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

# Mock pywebpush before importing anything that touches api.push
sys.modules.setdefault("pywebpush", MagicMock())

from . import approvals  # noqa: E402
from .audit import _redact  # noqa: E402
from .llm import _run_tool_block, _ToolRouter  # noqa: E402

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
CARD_SUMMARY = {"title": "Send email", "fields": [["To", "sam@example.com"], ["Subject", "Late"]], "body": "Running late"}


def _row(**overrides):
    row = {
        "id": "a1", "kind": "gmail.send", "summary": CARD_SUMMARY, "status": "pending",
        "created_at": NOW, "expires_at": NOW + timedelta(hours=12),
    }
    row.update(overrides)
    return row


@pytest.fixture
def pool():
    p = MagicMock()
    p.pool = AsyncMock()
    return p


class TestCreate:
    @pytest.mark.asyncio
    async def test_stores_params_and_returns_card(self, pool):
        pool.pool.fetchrow.return_value = _row()
        params = {"to": ["sam@example.com"], "subject": "Late", "body": "Running late"}
        card = await approvals.create_pending_action(pool, "ron", "gmail.send", params, CARD_SUMMARY)

        assert card["id"] == "a1"
        assert card["title"] == "Send email"
        assert card["fields"] == [["To", "sam@example.com"], ["Subject", "Late"]]
        assert card["body"] == "Running late"
        args = pool.pool.fetchrow.call_args.args
        # dicts go straight to the JSONB codec (manual json.dumps would double-encode)
        assert args[2:6] == ("ron", "gmail.send", params, CARD_SUMMARY)
        assert args[6] == approvals.APPROVAL_TTL

    @pytest.mark.asyncio
    async def test_capture_collects_cards_only_inside_the_context(self, pool):
        pool.pool.fetchrow.return_value = _row()
        with approvals.capture_pending_actions() as created:
            await approvals.create_pending_action(pool, "ron", "gmail.send", {}, CARD_SUMMARY)
        assert [c["id"] for c in created] == ["a1"]
        # Outside a capture block, creating still works and isn't collected anywhere.
        await approvals.create_pending_action(pool, "ron", "gmail.send", {}, CARD_SUMMARY)
        assert len(created) == 1


class TestApprove:
    @pytest.mark.asyncio
    async def test_runs_the_executor_and_records_the_result(self, pool):
        pool.pool.fetchrow.return_value = {"kind": "gmail.send", "params": {"to": ["sam@example.com"]}}
        executor = AsyncMock(return_value="Email sent to sam@example.com.")
        with patch.object(approvals, "_executor", return_value=executor), \
             patch("api.deps.get_user_permissions", AsyncMock(return_value=["email", "email_send"])):
            result = await approvals.approve(pool, "ron", "a1")

        assert result == {"id": "a1", "status": "done", "result": "Email sent to sam@example.com."}
        executor.assert_awaited_once_with(pool, "ron", "gmail.send", {"to": ["sam@example.com"]})
        claim_sql = pool.pool.fetchrow.call_args.args[0]
        assert "status = 'pending'" in claim_sql and "expires_at > NOW()" in claim_sql and "user_id = $2" in claim_sql
        pool.pool.execute.assert_awaited_with(ANY, "a1", "done", "Email sent to sam@example.com.")

    @pytest.mark.asyncio
    async def test_executor_error_marks_failed_with_its_message(self, pool):
        pool.pool.fetchrow.return_value = {"kind": "gmail.send", "params": {}}
        executor = AsyncMock(side_effect=approvals.ApprovalError("Google isn't connected any more"))
        with patch.object(approvals, "_executor", return_value=executor), \
             patch("api.deps.get_user_permissions", AsyncMock(return_value=["email_send"])):
            result = await approvals.approve(pool, "ron", "a1")
        assert result["status"] == "failed"
        assert "isn't connected" in result["result"]

    @pytest.mark.asyncio
    async def test_failure_before_anything_happened_goes_back_to_pending(self, pool):
        pool.pool.fetchrow.return_value = {"kind": "gmail.send", "params": {}}
        executor = AsyncMock(side_effect=approvals.ApprovalRetryable("Reconnect Google, then tap Send again."))
        with patch.object(approvals, "_executor", return_value=executor), \
             patch("api.deps.get_user_permissions", AsyncMock(return_value=["email_send"])):
            result = await approvals.approve(pool, "ron", "a1")
        assert result == {"id": "a1", "status": "pending", "result": "Reconnect Google, then tap Send again."}
        sql = pool.pool.execute.call_args.args[0]
        assert "status = 'pending'" in sql and "decided_at = NULL" in sql

    @pytest.mark.asyncio
    async def test_unexpected_error_never_leaves_it_stuck_in_approved(self, pool):
        pool.pool.fetchrow.return_value = {"kind": "calendar.create", "params": {}}
        executor = AsyncMock(side_effect=KeyError("event"))
        with patch.object(approvals, "_executor", return_value=executor), \
             patch("api.deps.get_user_permissions", AsyncMock(return_value=["calendar_write"])):
            result = await approvals.approve(pool, "ron", "a1")
        assert result["status"] == "failed"
        pool.pool.execute.assert_awaited_with(ANY, "a1", "failed", ANY)

    @pytest.mark.asyncio
    async def test_revoked_permission_is_refused_before_running(self, pool):
        pool.pool.fetchrow.return_value = {"kind": "gmail.send", "params": {}}
        executor = AsyncMock()
        with patch.object(approvals, "_executor", return_value=executor), \
             patch("api.deps.get_user_permissions", AsyncMock(return_value=["email"])):
            with pytest.raises(approvals.ApprovalForbidden):
                await approvals.approve(pool, "ron", "a1")
        executor.assert_not_awaited()
        pool.pool.execute.assert_awaited_with(ANY, "a1", "failed", ANY)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lookup,exc", [
        (None, approvals.ApprovalNotFound),  # unknown id, or someone else's
        ({"status": "done", "expired": False}, approvals.ApprovalNotPending),
        ({"status": "pending", "expired": True}, approvals.ApprovalExpired),
    ])
    async def test_unclaimable_actions_explain_why(self, pool, lookup, exc):
        pool.pool.fetchrow.side_effect = [None, lookup]
        with pytest.raises(exc):
            await approvals.approve(pool, "ron", "a1")

    @pytest.mark.asyncio
    async def test_reject(self, pool):
        pool.pool.fetchrow.return_value = {"id": "a1"}
        result = await approvals.reject(pool, "ron", "a1")
        assert result["status"] == "rejected"

    def test_required_permission(self):
        assert approvals.required_permission("gmail.send") == "email_send"
        assert approvals.required_permission("gmail.reply") == "email_send"
        assert approvals.required_permission("calendar.delete") == "calendar_write"
        assert approvals.required_permission("something.else") is None


class TestToolLoopIntegration:
    """A tool that drafts an action surfaces it to the stream, or pushes elsewhere."""

    def _drafting_router(self, pool):
        tool = MagicMock()
        tool.name = "gmail"
        tool.description = "Gmail"
        tool.parameters = {"type": "object", "properties": {}}

        async def draft(**_):
            card = await approvals.create_pending_action(pool, "ron", "gmail.send", {}, CARD_SUMMARY)
            return f"waiting ({card['id']})"

        tool.execute = draft
        block = MagicMock()
        block.name = "gmail"
        block.input = {"action": "send_email"}
        return _ToolRouter({"gmail": tool}, []), block

    @pytest.mark.asyncio
    async def test_event_stream_gets_the_card_and_no_push(self, pool):
        pool.pool.fetchrow.return_value = _row()
        router, block = self._drafting_router(pool)
        out: list[dict] = []
        with patch("api.llm.notify_pending", AsyncMock()) as notify:
            result = await _run_tool_block(block, router, db_pool=pool, user_id="ron", channel="pwa", approvals_out=out)
        assert result == "waiting (a1)"
        assert [c["id"] for c in out] == ["a1"]
        notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_other_surfaces_push_a_notification(self, pool):
        pool.pool.fetchrow.return_value = _row()
        router, block = self._drafting_router(pool)
        with patch("api.llm.notify_pending", AsyncMock()) as notify:
            await _run_tool_block(block, router, db_pool=pool, user_id="ron", channel="voice")
        notify.assert_awaited_once()
        assert notify.call_args.args[2][0]["id"] == "a1"


class TestAuditRedaction:
    def test_email_body_is_not_logged(self):
        params = {"action": "send_email", "to": ["sam@example.com"], "body": "secret plans"}
        logged = _redact("gmail", params)
        assert logged["body"] == "<12 chars>"
        assert logged["to"] == ["sam@example.com"]
        assert params["body"] == "secret plans"  # caller's dict untouched

    def test_other_tools_unchanged(self):
        params = {"body": "x"}
        assert _redact("weather", params) is params
