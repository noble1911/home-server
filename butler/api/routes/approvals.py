"""Tap-to-approve routes: list, approve and reject pending actions.

These are the only way a drafted email or calendar change gets executed —
the LLM has no tool that reaches them.
"""

from fastapi import APIRouter, Depends, HTTPException

from tools import DatabasePool

from .. import approvals
from ..deps import get_current_user, get_db_pool
from ..models import ApprovalResult, PendingApproval, PendingApprovalsResponse

router = APIRouter()


@router.get("", response_model=PendingApprovalsResponse)
async def list_pending_approvals(
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Pending, unexpired actions waiting for this user's approval."""
    items = await approvals.list_pending(pool, user_id)
    return PendingApprovalsResponse(approvals=[PendingApproval(**a) for a in items])


def _http_error(e: Exception) -> HTTPException:
    if isinstance(e, approvals.ApprovalNotFound):
        return HTTPException(404, "Approval not found")
    if isinstance(e, approvals.ApprovalNotPending):
        return HTTPException(409, f"Already {e.status}")
    if isinstance(e, approvals.ApprovalExpired):
        return HTTPException(410, "This approval has expired — ask Butler again")
    if isinstance(e, approvals.ApprovalForbidden):
        return HTTPException(403, "You no longer have permission for this")
    raise e


@router.post("/{action_id}/approve", response_model=ApprovalResult)
async def approve_action(
    action_id: str,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    try:
        return ApprovalResult(**await approvals.approve(pool, user_id, action_id))
    except (approvals.ApprovalNotFound, approvals.ApprovalNotPending,
            approvals.ApprovalExpired, approvals.ApprovalForbidden) as e:
        raise _http_error(e) from e


@router.post("/{action_id}/reject", response_model=ApprovalResult)
async def reject_action(
    action_id: str,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    try:
        return ApprovalResult(**await approvals.reject(pool, user_id, action_id))
    except (approvals.ApprovalNotFound, approvals.ApprovalNotPending,
            approvals.ApprovalExpired) as e:
        raise _http_error(e) from e
