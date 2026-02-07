"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    port: int = 8000

    # Database (same Immich PostgreSQL used by nanobot tools)
    database_url: str = "postgresql://postgres:postgres@localhost:5432/immich"

    # Claude API
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # LiveKit (must match voice-stack/livekit.yaml)
    livekit_url: str = "ws://livekit:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"

    # JWT auth for PWA users
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 1  # Access token: 1 hour (auto-refreshed by PWA)
    jwt_refresh_expire_hours: int = 4320  # Refresh token: 180 days

    # Invite codes (comma-separated, for household registration)
    invite_codes: str = "BUTLER-001"

    # Home Assistant (passed through to tools)
    home_assistant_url: str = ""
    home_assistant_token: str = ""

    # Weather (OpenWeatherMap)
    openweathermap_api_key: str = ""

    # Radarr (movie management)
    radarr_url: str = ""
    radarr_api_key: str = ""

    # Readarr (book management)
    readarr_url: str = ""
    readarr_api_key: str = ""

    # Sonarr (TV series management)
    sonarr_url: str = ""
    sonarr_api_key: str = ""

    # Jellyfin (media playback)
    jellyfin_url: str = ""
    jellyfin_api_key: str = ""

    # Immich (photo search, read-only)
    immich_url: str = ""
    immich_api_key: str = ""

    # Service-to-service auth (LiveKit Agents -> butler-api)
    internal_api_key: str = ""

    # Ollama (for local embeddings)
    ollama_url: str = ""

    # Audiobookshelf (user provisioning)
    audiobookshelf_url: str = ""
    audiobookshelf_admin_token: str = ""

    # Nextcloud (user provisioning via OCS API)
    nextcloud_url: str = ""
    nextcloud_admin_user: str = ""
    nextcloud_admin_password: str = ""

    # Calibre-Web (user provisioning via admin form)
    calibreweb_url: str = ""
    calibreweb_admin_user: str = ""
    calibreweb_admin_password: str = ""

    # Health & storage monitoring
    external_drive_path: str = "/mnt/external"
    storage_thresholds: str = "70,80,90"
    health_check_timeout: int = 5
    prowlarr_api_key: str = ""

    # Cleanup jobs
    cleanup_retention_days: int = 30

    # Rate limiting (requests per minute per user/IP)
    rate_limit_enabled: bool = True
    rate_limit_auth: int = 5       # Auth endpoints (brute-force protection)
    rate_limit_chat: int = 20      # Chat endpoints (Claude API cost control)
    rate_limit_voice: int = 30     # Voice endpoints
    rate_limit_default: int = 60   # All other endpoints

    # Google OAuth (for Calendar, Gmail, etc.)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/oauth/google/callback"
    oauth_frontend_url: str = "http://localhost:5173"

    # WhatsApp Gateway (outbound notifications)
    whatsapp_gateway_url: str = ""

    # Home Assistant webhook authentication
    ha_webhook_secret: str = ""

    # Web Push (VAPID keys for PWA push notifications)
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@homeserver.local"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
