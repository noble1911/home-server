-- Migration 020: Dispatcharr sign-in for the IPTV sync (#223)
--
-- Butler signs in to Dispatcharr to push the IPTV provider. By default it uses
-- the admin's service login, but that isn't always usable (older accounts don't
-- store one, and Nextcloud's password rules can force a different password), so
-- an admin can set a Dispatcharr login explicitly. Blank = use the service login.
--
-- Idempotent: safe to re-run (migrations run on every startup).

ALTER TABLE butler.iptv_provider
    ADD COLUMN IF NOT EXISTS dispatcharr_username TEXT,
    ADD COLUMN IF NOT EXISTS dispatcharr_password_encrypted TEXT;
