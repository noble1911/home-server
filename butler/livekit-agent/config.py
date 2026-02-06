"""LiveKit Agent configuration from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    livekit_url: str = "ws://livekit:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"
    groq_api_key: str = ""
    kokoro_url: str = "http://kokoro-tts:8880"
    butler_api_url: str = "http://butler-api:8000"
    butler_api_key: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
