"""Webhook receiver endpoints for external service integrations.

POST /api/webhooks/homeassistant — Accept events from Home Assistant automations

Home Assistant sends events when automations fire or device states change.
Butler stores these for conversational context and optionally sends WhatsApp
notifications for significant events.

Authentication:
    Requests must include an ``X-Webhook-Secret`` header matching the
    ``HA_WEBHOOK_SECRET`` environment variable.  This is a shared secret
    configured in both HA and Butler.

HA Automation Example (configuration.yaml):
    automation:
      - alias: "Notify Butler on motion"
        trigger:
          - platform: state
            entity_id: binary_sensor.front_door_motion
            to: "on"
        action:
          - service: rest_command.butler_webhook
            data:
              event_type: state_changed
              entity_id: binary_sensor.front_door_motion
              new_state: "on"
              attributes:
                friendly_name: Front Door Motion
              notify: true
              message: "Motion detected at the front door"

    rest_command:
      butler_webhook:
        url: "http://butler-api:8000/api/webhooks/homeassistant"
        method: POST
        headers:
          X-Webhook-Secret: "{{ states('input_text.butler_webhook_secret') }}"
        content_type: application/json
        payload: "{{ data | to_json }}"
"""

from __future__ import annotations


import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from tools import DatabasePool, Tool, WhatsAppTool

from ..config import settings
from ..deps import get_db_pool, get_tools
from ..models import HAWebhookEvent, HAWebhookResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# ----------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------


async def verify_webhook_secret(
    x_webhook_secret: Annotated[str | None, Header()] = None,
) -> None:
    """Validate that the incoming request carries the correct shared secret."""
    if not settings.ha_webhook_secret:
        raise HTTPException(
            503,
            "Webhook endpoint is not configured (HA_WEBHOOK_SECRET not set)",
        )
    if not x_webhook_secret or x_webhook_secret != settings.ha_webhook_secret:
        raise HTTPException(401, "Invalid or missing webhook secret")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


async def _store_event(
    pool: DatabasePool,
    event: HAWebhookEvent,
) -> int:
    """Persist a Home Assistant event and return its row id."""
    db = pool.pool
    row = await db.fetchrow(
        """
        INSERT INTO butler.ha_events
            (event_type, entity_id, old_state, new_state, attributes)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        RETURNING id
        """,
        event.event_type,
        event.entity_id,
        event.old_state,
        event.new_state,
        event.attributes,
    )
    return row["id"]


async def _notify_users(
    pool: DatabasePool,
    whatsapp: WhatsAppTool,
    message: str,
) -> bool:
    """Send a smart_home notification to all eligible users.

    Eligible = phone configured AND smart_home category enabled.
    The WhatsApp tool's own execute() handles preference checks, rate
    limiting, and quiet hours for each user individually.

    Returns True if at least one notification was sent.
    """
    db = pool.pool
    rows = await db.fetch(
        """
        SELECT id FROM butler.users
        WHERE phone IS NOT NULL
          AND phone != ''
        """,
    )

    any_sent = False
    for row in rows:
        result = await whatsapp.execute(
            action="send_message",
            user_id=row["id"],
            message=message,
            category="smart_home",
        )
        if "sent" in result.lower() or "queued" in result.lower():
            any_sent = True
        else:
            logger.debug("WhatsApp skip for %s: %s", row["id"], result)

    return any_sent


def _build_notification_message(event: HAWebhookEvent) -> str:
    """Build a human-readable notification from the event.

    If the caller included a ``message`` in attributes, use that directly.
    Otherwise, generate a sensible default from the event fields.
    """
    custom_msg = event.attributes.get("message")
    if custom_msg:
        return custom_msg

    friendly = event.attributes.get("friendly_name", event.entity_id or "Unknown")
    if event.event_type == "automation_triggered":
        return f"Automation triggered: {friendly}"
    if event.new_state and event.old_state:
        return f"{friendly} changed from {event.old_state} to {event.new_state}"
    if event.new_state:
        return f"{friendly} is now {event.new_state}"
    return f"Home Assistant event: {event.event_type} ({friendly})"


# ----------------------------------------------------------------------
# Endpoint
# ----------------------------------------------------------------------


@router.post("/homeassistant", response_model=HAWebhookResponse)
async def receive_ha_event(
    event: HAWebhookEvent,
    _secret: None = Depends(verify_webhook_secret),
    pool: DatabasePool = Depends(get_db_pool),
    tools: dict[str, Tool] = Depends(get_tools),
):
    """Receive and process a Home Assistant webhook event.

    The event is always stored for conversational context (so Butler can
    reference "the motion sensor triggered 5 minutes ago").

    A WhatsApp notification is sent when:
    - The payload includes ``attributes.notify: true``, OR
    - The event_type is ``automation_triggered`` (always noteworthy)

    HA automations control *which* events are significant by choosing
    what to send — Butler just receives, stores, and notifies.
    """
    # 1. Store the event
    event_id = await _store_event(pool, event)
    logger.info(
        "HA event stored: id=%d type=%s entity=%s",
        event_id,
        event.event_type,
        event.entity_id,
    )

    # 2. Decide whether to notify
    should_notify = (
        event.attributes.get("notify", False)
        or event.event_type == "automation_triggered"
    )

    notification_sent = False
    if should_notify:
        whatsapp: WhatsAppTool | None = tools.get("whatsapp")
        if whatsapp:
            message = _build_notification_message(event)
            notification_sent = await _notify_users(pool, whatsapp, message)

            # Mark the event as having triggered a notification
            await pool.pool.execute(
                "UPDATE butler.ha_events SET notification_sent = $1, processed = TRUE WHERE id = $2",
                notification_sent,
                event_id,
            )
        else:
            logger.debug("WhatsApp tool not configured — skipping notification")
    else:
        # Mark as processed but no notification
        await pool.pool.execute(
            "UPDATE butler.ha_events SET processed = TRUE WHERE id = $1",
            event_id,
        )

    return HAWebhookResponse(
        status="accepted",
        event_id=event_id,
        notification_sent=notification_sent,
    )
