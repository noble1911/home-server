-- Migration 016: Send to Kindle address (#213)
--
-- The user's Amazon "Send to Kindle" address (…@kindle.com). Butler only ever
-- emails books to this stored address, never to one the model supplies.
--
-- Idempotent: safe to re-run (migrations run on every startup).

ALTER TABLE butler.users
    ADD COLUMN IF NOT EXISTS kindle_email TEXT;
