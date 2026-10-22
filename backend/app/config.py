"""Application settings, loaded from environment variables and `.env`."""

import logging
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    environment: Literal["development", "test", "demo", "production"] = Field(
        default="development", validation_alias="ENVIRONMENT"
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    database_url: str = Field(default="sqlite:///./data/app.db", validation_alias="DATABASE_URL")
    # When false, message text is not stored.
    store_transcripts: bool = Field(default=True, validation_alias="STORE_TRANSCRIPTS")
    retention_days: int = Field(default=30, ge=0, validation_alias="RETENTION_DAYS")
    retention_interval_hours: float = Field(default=24, ge=0, validation_alias="RETENTION_INTERVAL_HOURS")

    jwt_secret: str = Field(default="", validation_alias="JWT_SECRET")
    jwt_expire_minutes: int = Field(default=480, ge=5, validation_alias="JWT_EXPIRE_MINUTES")
    allow_registration: bool = Field(default=True, validation_alias="ALLOW_REGISTRATION")

    # Number of recent messages passed to the reply provider.
    context_messages: int = Field(default=8, ge=1, validation_alias="CONTEXT_MESSAGES")

    max_message_chars: int = Field(default=2000, ge=1, validation_alias="MAX_MESSAGE_CHARS")
    max_messages_per_session: int = Field(default=100, ge=2, validation_alias="MAX_MESSAGES_PER_SESSION")
    rate_limit_per_minute: int = Field(default=10, ge=1, validation_alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(default=120, ge=1, validation_alias="RATE_LIMIT_PER_HOUR")

    cors_origins: str = Field(default="http://localhost:5173", validation_alias="CORS_ORIGINS")
    enable_api_docs: bool = Field(default=True, validation_alias="ENABLE_API_DOCS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        if len(self.jwt_secret) < MIN_JWT_SECRET_LENGTH:
            if self.is_production:
                raise ValueError(f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters in production")
            # Non-production only: tokens become invalid when the process restarts.
            self.jwt_secret = secrets.token_urlsafe(48)
            logger.warning("JWT_SECRET is not set; using a temporary key (sign-ins reset on restart)")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def api_docs_enabled(self) -> bool:
        return self.enable_api_docs and not self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()
