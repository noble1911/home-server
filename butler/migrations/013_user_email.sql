-- Add email address to user profiles.
-- Used as the canonical email for Immich and other services that require one.

ALTER TABLE butler.users
    ADD COLUMN IF NOT EXISTS email TEXT;
