-- Add per-user tool permissions
-- Each user gets a JSONB array of permission group names that controls
-- which tools the LLM can use on their behalf.

ALTER TABLE butler.users
    ADD COLUMN IF NOT EXISTS permissions JSONB NOT NULL DEFAULT '["media", "home"]';
