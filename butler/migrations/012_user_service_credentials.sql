-- Store service credentials on user record for re-provisioning.
-- These are the shared username + password chosen during onboarding,
-- encrypted with Fernet (same as service_credentials.password_encrypted).

ALTER TABLE butler.users
    ADD COLUMN IF NOT EXISTS service_username TEXT,
    ADD COLUMN IF NOT EXISTS service_password_encrypted TEXT;
