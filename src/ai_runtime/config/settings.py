"""Typed settings loaded from `AI_RUNTIME_` environment variables."""

from enum import StrEnum
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DATABASE_URL = "postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_ASYNC_POSTGRES_SCHEME = "postgresql+asyncpg://"
_REDIS_SCHEMES = ("redis://", "rediss://")


class Environment(StrEnum):
    """Deployment environments recognized by AI Runtime."""

    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Immutable application settings sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="AI_RUNTIME_",
        frozen=True,
    )

    app_name: str = "AI Runtime"
    environment: Environment = Environment.LOCAL
    debug: bool = False
    log_level: str = "INFO"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    database_url: str = _DEFAULT_DATABASE_URL
    redis_url: str = _DEFAULT_REDIS_URL
    rate_limit_requests_per_minute: int = 60
    rate_limit_burst: int = 60
    idempotency_ttl_seconds: int = 86400

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Require the async SQLAlchemy + asyncpg PostgreSQL URL scheme."""
        if not value.startswith(_ASYNC_POSTGRES_SCHEME):
            msg = f"database_url must start with {_ASYNC_POSTGRES_SCHEME!r}"
            raise ValueError(msg)
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        """Require a redis:// or rediss:// URL."""
        if not value.startswith(_REDIS_SCHEMES):
            msg = "redis_url must start with 'redis://' or 'rediss://'"
            raise ValueError(msg)
        return value

    @field_validator("rate_limit_requests_per_minute", "rate_limit_burst", "idempotency_ttl_seconds")
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        """Require positive integers for rate-limit and idempotency settings."""
        if value <= 0:
            msg = "must be greater than zero"
            raise ValueError(msg)
        return value
