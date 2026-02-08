"""Push notification subscription management routes."""

from fastapi import APIRouter, Depends, Query

from tools import DatabasePool

from ..config import settings
from ..deps import get_current_user, get_db_pool
from ..models import PushSubscribeRequest, PushSubscriptionInfo
from ..push import send_push_to_user

router = APIRouter()


@router.get("/vapid-key")
async def get_vapid_key():
    """Return the public VAPID key for push subscription.

    No auth required — the browser needs this to call pushManager.subscribe().
    """
    return {"vapidPublicKey": settings.vapid_public_key}


@router.post("/subscribe", status_code=201)
async def subscribe(
    req: PushSubscribeRequest,
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Store a push subscription for the authenticated user."""
    db = pool.pool
    await db.execute(
        """
        INSERT INTO butler.push_subscriptions (user_id, endpoint, key_p256dh, key_auth)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, endpoint) DO UPDATE SET
            key_p256dh = EXCLUDED.key_p256dh,
            key_auth   = EXCLUDED.key_auth,
            last_used_at = NOW()
        """,
        user_id,
        req.endpoint,
        req.keys.p256dh,
        req.keys.auth,
    )
    return {"status": "subscribed"}


@router.delete("/subscribe")
async def unsubscribe(
    endpoint: str = Query(..., description="The push subscription endpoint URL to remove"),
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Remove a push subscription for the authenticated user."""
    db = pool.pool
    await db.execute(
        "DELETE FROM butler.push_subscriptions WHERE user_id = $1 AND endpoint = $2",
        user_id,
        endpoint,
    )
    return {"status": "unsubscribed"}


@router.get("/subscriptions", response_model=list[PushSubscriptionInfo])
async def list_subscriptions(
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """List all push subscriptions for the authenticated user."""
    db = pool.pool
    rows = await db.fetch(
        "SELECT id, endpoint, created_at FROM butler.push_subscriptions WHERE user_id = $1",
        user_id,
    )
    return [
        PushSubscriptionInfo(
            id=r["id"],
            endpoint=r["endpoint"],
            createdAt=r["created_at"].isoformat(),
        )
        for r in rows
    ]


@router.post("/test")
async def test_push(
    user_id: str = Depends(get_current_user),
    pool: DatabasePool = Depends(get_db_pool),
):
    """Send a test push notification to the authenticated user's devices."""
    count = await send_push_to_user(
        pool=pool,
        user_id=user_id,
        title="Butler Test",
        body="Push notifications are working!",
        url="/settings",
        category="general",
    )
    return {"sent": count}
