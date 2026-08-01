"""Typed settings loaded from `AI_RUNTIME_` environment variables."""

from enum import StrEnum
from pydantic_settings import BaseSettings, SettingsConfigDict


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
