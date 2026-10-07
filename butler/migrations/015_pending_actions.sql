-- Migration 015: Tap-to-approve pending actions
--
-- Side-effecting tools (sending email, changing the calendar) don't act
-- directly. They store what they would do here, and only run once the user
-- approves it in the app (POST /api/approvals/{id}/approve). The model can
-- create a pending action but has no way to approve one.
--
-- Idempotent: safe to re-run (migrations run on every startup).

CREATE TABLE IF NOT EXISTS butler.pending_actions (
    id TEXT PRIMARY KEY,                -- random URL-safe token
    user_id TEXT NOT NULL REFERENCES butler.users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,                 -- e.g. 'gmail.send', 'calendar.update'
    params JSONB NOT NULL,              -- exactly what will be executed on approval
    summary JSONB NOT NULL,             -- what the approval card shows
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected | done | failed
    result TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    decided_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pending_actions_user_status
    ON butler.pending_actions (user_id, status, created_at DESC);
