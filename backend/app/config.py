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

    # Conversational AI (OpenAI). Without a key, low-risk messages get 503 reply_unavailable;
    # escalated messages still get the reviewed support response.
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    # Cheapest model that tested well for this use; a non-reasoning model keeps replies fast.
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")
    ai_timeout_seconds: float = Field(default=20.0, gt=0, validation_alias="AI_TIMEOUT_SECONDS")
    ai_max_retries: int = Field(default=1, ge=0, le=5, validation_alias="AI_MAX_RETRIES")
    ai_max_output_tokens: int = Field(default=300, ge=16, validation_alias="AI_MAX_OUTPUT_TOKENS")
    # Empty means "not sent" (some models only accept their default temperature).
    ai_temperature: float | None = Field(default=0.6, ge=0, le=2, validation_alias="AI_TEMPERATURE")
    # Second safety opinion from the OpenAI Moderation API (free). Input moderation fails closed.
    use_openai_moderation: bool = Field(default=True, validation_alias="USE_OPENAI_MODERATION")
    # USD per 1 million tokens, for cost estimates only. Check current OpenAI pricing for the model.
    price_input_per_million: float = Field(default=0.15, ge=0, validation_alias="PRICE_INPUT_PER_MILLION")
    price_output_per_million: float = Field(default=0.60, ge=0, validation_alias="PRICE_OUTPUT_PER_MILLION")
    # Optional monthly AI spending cap in USD. When reached, AI replies stop until the next month.
    ai_monthly_budget_usd: float | None = Field(default=None, gt=0, validation_alias="AI_MONTHLY_BUDGET_USD")

    max_message_chars: int = Field(default=2000, ge=1, validation_alias="MAX_MESSAGE_CHARS")
    max_messages_per_session: int = Field(default=100, ge=2, validation_alias="MAX_MESSAGES_PER_SESSION")
    rate_limit_per_minute: int = Field(default=10, ge=1, validation_alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(default=120, ge=1, validation_alias="RATE_LIMIT_PER_HOUR")

    cors_origins: str = Field(default="http://localhost:5173", validation_alias="CORS_ORIGINS")
    enable_api_docs: bool = Field(default=True, validation_alias="ENABLE_API_DOCS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _empty_means_unset(cls, data):
        # `AI_TEMPERATURE=` or `AI_MONTHLY_BUDGET_USD=` in .env means "not set", not an invalid number.
        if isinstance(data, dict):
            for key in ("AI_TEMPERATURE", "ai_temperature", "AI_MONTHLY_BUDGET_USD", "ai_monthly_budget_usd"):
                if data.get(key) == "":
                    data[key] = None
        return data

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
    def ai_configured(self) -> bool:
        return bool(self.openai_api_key.strip())

    @property
    def moderation_enabled(self) -> bool:
        return self.use_openai_moderation and self.ai_configured

    @property
    def api_docs_enabled(self) -> bool:
        return self.enable_api_docs and not self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()
