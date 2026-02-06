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

    # Service-to-service auth (LiveKit Agents -> butler-api)
    internal_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
