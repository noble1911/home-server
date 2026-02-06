-- Alert state tracking for health and storage monitoring.
-- Prevents notification spam by recording threshold crossings.
--
-- Usage:
--   docker exec immich-postgres psql -U postgres -d immich -f /app/migrations/003_alert_state.sql

CREATE TABLE IF NOT EXISTS butler.alert_state (
    id              SERIAL PRIMARY KEY,
    alert_key       TEXT NOT NULL UNIQUE,        -- e.g. "storage:external:80", "health:jellyfin:down"
    alert_type      TEXT NOT NULL,               -- "storage_threshold" or "service_down"
    severity        TEXT NOT NULL,               -- "warning", "critical", "emergency"
    message         TEXT NOT NULL,               -- Human-readable alert message
    first_triggered_at TIMESTAMPTZ DEFAULT NOW(),
    last_triggered_at  TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,                 -- NULL = still active
    notification_sent  BOOLEAN DEFAULT FALSE,    -- Whether notification was dispatched
    metadata        JSONB DEFAULT '{}'           -- Extra context (threshold %, service name, etc.)
);

-- Fast lookup of active (unresolved) alerts by type
CREATE INDEX IF NOT EXISTS idx_alert_state_active
    ON butler.alert_state(alert_type)
    WHERE resolved_at IS NULL;
