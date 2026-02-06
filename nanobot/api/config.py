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
    jwt_expire_hours: int = 720  # 30 days

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

    # Sonarr (TV series management)
    sonarr_url: str = ""
    sonarr_api_key: str = ""

    # Jellyfin (media playback)
    jellyfin_url: str = ""
    jellyfin_api_key: str = ""

    # Service-to-service auth (LiveKit Agents -> butler-api)
    internal_api_key: str = ""

    # Ollama (for local embeddings)
    ollama_url: str = ""

    # Google OAuth (for Calendar, Gmail, etc.)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/oauth/google/callback"
    oauth_frontend_url: str = "http://localhost:5173"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
