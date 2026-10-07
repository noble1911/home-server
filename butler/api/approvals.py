"""Tap-to-approve pending actions.

Side-effecting tools (sending email, changing the calendar) don't act when the
model calls them. They call create_pending_action(), which stores exactly what
would be executed and returns a card for the app to show. Only an explicit
approval from the user (POST /api/approvals/{id}/approve) runs the action, so
the model can propose but never carry out a send or a calendar change on its
own — even if an email it read tells it to.

Executors live next to the tools that draft them; each tool module exposes
``execute_approved(pool, user_id, kind, params) -> str`` and raises
ApprovalError with a user-facing message when it can't complete.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

APPROVAL_TTL = timedelta(hours=12)

# kind prefix -> permission group required to draft *and* to approve
KIND_PERMISSIONS: dict[str, str] = {
    "gmail": "email_send",
    "calendar": "calendar_write",
}


class ApprovalError(Exception):
    """An approved action couldn't be completed; the message is shown to the user."""


class ApprovalRetryable(ApprovalError):
    """Failed before anything was sent or changed (e.g. Google needs reconnecting).

    The action goes back to pending so the user can fix the cause and tap again.
    """


class ApprovalNotFound(Exception):
    pass


class ApprovalNotPending(Exception):
    def __init__(self, status: str):
        super().__init__(status)
        self.status = status


class ApprovalExpired(Exception):
    pass


class ApprovalForbidden(Exception):
    pass


# Pending actions created during the current tool call, so the chat stream can
# surface them as events without every tool returning structured data.
_captured: ContextVar[list[dict] | None] = ContextVar("pending_actions_captured", default=None)


@contextmanager
def capture_pending_actions() -> Iterator[list[dict]]:
    created: list[dict] = []
    token = _captured.set(created)
    try:
        yield created
    finally:
        _captured.reset(token)


def required_permission(kind: str) -> str | None:
    return KIND_PERMISSIONS.get(kind.split(".", 1)[0])


def _public(row) -> dict[str, Any]:
    summary = row["summary"] or {}
    return {
        "id": row["id"],
        "kind": row["kind"],
        "title": summary.get("title", row["kind"]),
        "fields": summary.get("fields", []),
        "body": summary.get("body"),
        "status": row["status"],
        "createdAt": row["created_at"].isoformat(),
        "expiresAt": row["expires_at"].isoformat(),
    }


async def create_pending_action(
    pool,
    user_id: str,
    kind: str,
    params: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Store a proposed action and return its public card.

    ``summary`` is ``{"title": str, "fields": [[label, value], ...], "body": str | None}``.
    """
    action_id = secrets.token_urlsafe(12)
    row = await pool.pool.fetchrow(
        """
        INSERT INTO butler.pending_actions (id, user_id, kind, params, summary, expires_at)
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, NOW() + $6::interval)
        RETURNING id, kind, summary, status, created_at, expires_at
        """,
        action_id, user_id, kind, params, summary, APPROVAL_TTL,
    )
    card = _public(row)
    captured = _captured.get()
    if captured is not None:
        captured.append(card)
    logger.info("Pending action %s created: user=%s kind=%s", action_id, user_id, kind)
    return card


async def list_pending(pool, user_id: str) -> list[dict[str, Any]]:
    rows = await pool.pool.fetch(
        """
        SELECT id, kind, summary, status, created_at, expires_at
        FROM butler.pending_actions
        WHERE user_id = $1 AND status = 'pending' AND expires_at > NOW()
        ORDER BY created_at
        """,
        user_id,
    )
    return [_public(r) for r in rows]


async def _explain_missing(pool, user_id: str, action_id: str) -> Exception:
    row = await pool.pool.fetchrow(
        "SELECT status, expires_at <= NOW() AS expired FROM butler.pending_actions "
        "WHERE id = $1 AND user_id = $2",
        action_id, user_id,
    )
    if row is None:
        return ApprovalNotFound()
    if row["status"] != "pending":
        return ApprovalNotPending(row["status"])
    return ApprovalExpired()


async def reject(pool, user_id: str, action_id: str) -> dict[str, Any]:
    row = await pool.pool.fetchrow(
        """
        UPDATE butler.pending_actions SET status = 'rejected', decided_at = NOW()
        WHERE id = $1 AND user_id = $2 AND status = 'pending'
        RETURNING id
        """,
        action_id, user_id,
    )
    if row is None:
        raise await _explain_missing(pool, user_id, action_id)
    return {"id": action_id, "status": "rejected", "result": "Cancelled — nothing was sent or changed."}


async def approve(pool, user_id: str, action_id: str) -> dict[str, Any]:
    """Run an approved action once. Raises the Approval* exceptions above."""
    from .deps import get_user_permissions

    # Claim it atomically so a double tap can't run it twice.
    row = await pool.pool.fetchrow(
        """
        UPDATE butler.pending_actions SET status = 'approved', decided_at = NOW()
        WHERE id = $1 AND user_id = $2 AND status = 'pending' AND expires_at > NOW()
        RETURNING kind, params
        """,
        action_id, user_id,
    )
    if row is None:
        raise await _explain_missing(pool, user_id, action_id)

    kind, params = row["kind"], row["params"]
    perm = required_permission(kind)
    if perm and perm not in await get_user_permissions(pool, user_id):
        await _finish(pool, action_id, "failed", "You no longer have permission for this.")
        raise ApprovalForbidden()

    try:
        result = await _executor(kind)(pool, user_id, kind, params)
        status = "done"
    except ApprovalRetryable as e:
        await pool.pool.execute(
            "UPDATE butler.pending_actions SET status = 'pending', decided_at = NULL, result = $2 WHERE id = $1",
            action_id, str(e),
        )
        logger.info("Pending action %s not run, back to pending: %s", action_id, e)
        return {"id": action_id, "status": "pending", "result": str(e)}
    except ApprovalError as e:
        result, status = str(e), "failed"
    except Exception as e:  # never leave an action stuck in 'approved'
        logger.exception("Approved action %s (%s) failed", action_id, kind)
        result, status = f"Something went wrong: {e}", "failed"

    await _finish(pool, action_id, status, result)
    logger.info("Pending action %s %s: %s", action_id, status, result[:120])
    return {"id": action_id, "status": status, "result": result}


async def _finish(pool, action_id: str, status: str, result: str) -> None:
    await pool.pool.execute(
        "UPDATE butler.pending_actions SET status = $2, result = $3 WHERE id = $1",
        action_id, status, result,
    )


def _executor(kind: str):
    prefix = kind.split(".", 1)[0]
    if prefix == "gmail":
        from tools.gmail import execute_approved
    elif prefix == "calendar":
        from tools.google_calendar import execute_approved
    else:
        raise ApprovalError(f"Unknown action type: {kind}")
    return execute_approved


async def notify_pending(pool, user_id: str, actions: list[dict]) -> None:
    """Push a notification for approvals created outside the chat screen (e.g. voice)."""
    from .push import send_push_to_user

    for action in actions:
        detail = next((v for k, v in action["fields"] if k in ("To", "Event")), "")
        try:
            await send_push_to_user(
                pool, user_id,
                title=f"Approve: {action['title']}",
                body=detail or "Butler is waiting for your approval.",
                url="/",
                category="approval",
            )
        except Exception:
            logger.exception("Failed to push approval %s", action["id"])
