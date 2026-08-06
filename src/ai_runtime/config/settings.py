"""Typed settings loaded from `AI_RUNTIME_` environment variables."""

from enum import StrEnum
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DATABASE_URL = "postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime"
_ASYNC_POSTGRES_SCHEME = "postgresql+asyncpg://"


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
    database_url: str = _DEFAULT_DATABASE_URL

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Require the async SQLAlchemy + asyncpg PostgreSQL URL scheme."""
        if not value.startswith(_ASYNC_POSTGRES_SCHEME):
            msg = f"database_url must start with {_ASYNC_POSTGRES_SCHEME!r}"
            raise ValueError(msg)
        return value
