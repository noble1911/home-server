-- Add permissions to invite codes.
-- Admins choose which permissions a new user gets when generating an invite.
-- NULL = use default ("media", "home"), preserving backward compatibility.

ALTER TABLE butler.invite_codes
    ADD COLUMN IF NOT EXISTS permissions JSONB;
