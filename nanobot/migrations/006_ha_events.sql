-- Home Assistant webhook event storage.
-- Stores incoming HA events for context and audit trail, with notification
-- tracking to prevent duplicate alerts.

CREATE TABLE IF NOT EXISTS butler.ha_events (
    id            SERIAL PRIMARY KEY,
    event_type    TEXT NOT NULL,           -- e.g. "state_changed", "automation_triggered"
    entity_id     TEXT,                    -- e.g. "binary_sensor.front_door_motion"
    old_state     TEXT,                    -- previous state value (NULL for new entities)
    new_state     TEXT,                    -- current state value
    attributes    JSONB DEFAULT '{}',      -- full HA event attributes / extra data
    processed     BOOLEAN DEFAULT FALSE,   -- has Butler evaluated this event?
    notification_sent BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Fast lookups by entity and recency (common query: "what happened recently?")
CREATE INDEX IF NOT EXISTS idx_ha_events_entity_created
    ON butler.ha_events (entity_id, created_at DESC);

-- Find unprocessed events for the background evaluator
CREATE INDEX IF NOT EXISTS idx_ha_events_unprocessed
    ON butler.ha_events (processed) WHERE processed = FALSE;
