-- Tool Usage Audit Logging
-- Tracks every tool call for debugging, observability, and cost analysis.
--
-- Usage:
--   docker exec immich-postgres psql -U postgres -d immich -f /app/migrations/006_tool_usage.sql

CREATE TABLE IF NOT EXISTS butler.tool_usage (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT REFERENCES butler.users(id) ON DELETE SET NULL,
    tool_name       TEXT NOT NULL,
    parameters      JSONB DEFAULT '{}',
    result_summary  TEXT,
    error           TEXT,                           -- NULL = success
    duration_ms     INTEGER NOT NULL,
    channel         TEXT,                           -- 'pwa', 'voice', etc.
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Primary query: recent tool calls ordered by time
CREATE INDEX IF NOT EXISTS idx_tool_usage_created_at
    ON butler.tool_usage(created_at DESC);

-- Filter by user
CREATE INDEX IF NOT EXISTS idx_tool_usage_user_id
    ON butler.tool_usage(user_id);

-- Aggregation: most-used tools, error rates
CREATE INDEX IF NOT EXISTS idx_tool_usage_tool_name
    ON butler.tool_usage(tool_name);
