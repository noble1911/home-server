-- Butler Memory Schema
-- Runs in Immich's PostgreSQL instance (already has vector extensions)
--
-- Usage:
--   docker exec immich-postgres psql -U postgres -d immich -f /app/migrations/001_butler_schema.sql

-- Create butler schema (separate from immich data)
CREATE SCHEMA IF NOT EXISTS butler;

-- Users table: stores user identity and personality config
CREATE TABLE IF NOT EXISTS butler.users (
    id TEXT PRIMARY KEY,                    -- Unique identifier (phone number, telegram id, etc.)
    name TEXT NOT NULL,                     -- Display name
    soul JSONB DEFAULT '{}',                -- Personality/preference config
    phone TEXT,                             -- E.164 phone number for WhatsApp notifications
    notification_prefs JSONB NOT NULL       -- WhatsApp notification settings
        DEFAULT '{"enabled": true, "categories": ["download", "reminder", "weather", "smart_home", "calendar", "general"]}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- User facts: things Butler learns about users
CREATE TABLE IF NOT EXISTS butler.user_facts (
    id SERIAL PRIMARY KEY,
    user_id TEXT REFERENCES butler.users(id) ON DELETE CASCADE,
    fact TEXT NOT NULL,                     -- The fact itself
    category TEXT,                          -- preference, schedule, relationship, etc.
    confidence REAL DEFAULT 1.0,            -- How confident we are (0.0 - 1.0)
    source TEXT,                            -- Where we learned this (conversation, explicit, etc.)
    embedding VECTOR(1536),                 -- For semantic search (migrated to 768 in 002)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ                  -- Optional expiry for temporary facts
);

-- Conversation history: for context and learning
CREATE TABLE IF NOT EXISTS butler.conversation_history (
    id SERIAL PRIMARY KEY,
    user_id TEXT REFERENCES butler.users(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,                  -- whatsapp, telegram, voice, pwa
    role TEXT NOT NULL,                     -- user, assistant
    content TEXT NOT NULL,                  -- Message content
    metadata JSONB DEFAULT '{}',            -- Extra data (tool calls, etc.)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Scheduled tasks: for reminders and automations
CREATE TABLE IF NOT EXISTS butler.scheduled_tasks (
    id SERIAL PRIMARY KEY,
    user_id TEXT REFERENCES butler.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,                     -- Task name
    cron_expression TEXT,                   -- Cron schedule (NULL for one-time)
    action JSONB NOT NULL,                  -- What to do (message, tool call, etc.)
    enabled BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ===================
-- Indexes for performance
-- ===================

-- User facts queries
CREATE INDEX IF NOT EXISTS idx_user_facts_user_id
    ON butler.user_facts(user_id);
CREATE INDEX IF NOT EXISTS idx_user_facts_category
    ON butler.user_facts(category);
CREATE INDEX IF NOT EXISTS idx_user_facts_expires
    ON butler.user_facts(expires_at)
    WHERE expires_at IS NOT NULL;

-- Composite index for queries filtering by user_id AND category
-- More efficient than separate indexes for common access patterns
CREATE INDEX IF NOT EXISTS idx_user_facts_user_category
    ON butler.user_facts(user_id, category);

-- Vector similarity search index (HNSW for fast approximate nearest neighbor)
-- Uses cosine distance which works well for normalized embeddings
-- Note: Only indexes non-null embeddings to save space for facts without embeddings
CREATE INDEX IF NOT EXISTS idx_user_facts_embedding
    ON butler.user_facts
    USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

-- Conversation history queries
CREATE INDEX IF NOT EXISTS idx_conversation_history_user_id
    ON butler.conversation_history(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_history_created_at
    ON butler.conversation_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversation_history_channel
    ON butler.conversation_history(channel);

-- Scheduled tasks queries
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_user_id
    ON butler.scheduled_tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_next_run
    ON butler.scheduled_tasks(next_run)
    WHERE enabled = TRUE;

-- ===================
-- Functions
-- ===================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION butler.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to users table
DROP TRIGGER IF EXISTS users_updated_at ON butler.users;
CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON butler.users
    FOR EACH ROW
    EXECUTE FUNCTION butler.update_updated_at();

-- ===================
-- Sample data (optional)
-- ===================

-- Insert a default user for testing
INSERT INTO butler.users (id, name, soul)
VALUES ('default', 'Default User', '{"tone": "friendly", "verbosity": "concise"}')
ON CONFLICT (id) DO NOTHING;

-- Done!
-- Verify with: SELECT * FROM butler.users;
