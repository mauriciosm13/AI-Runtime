"""Settings loading and validation tests."""

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch
from ai_runtime.config.settings import Environment, Settings

_SETTINGS_ENV_VARS = (
    "AI_RUNTIME_APP_NAME",
    "AI_RUNTIME_ENVIRONMENT",
    "AI_RUNTIME_DEBUG",
    "AI_RUNTIME_LOG_LEVEL",
    "AI_RUNTIME_OPENAI_API_KEY",
    "AI_RUNTIME_OPENAI_BASE_URL",
    "AI_RUNTIME_DATABASE_URL",
    "AI_RUNTIME_REDIS_URL",
    "AI_RUNTIME_RATE_LIMIT_REQUESTS_PER_MINUTE",
    "AI_RUNTIME_RATE_LIMIT_BURST",
    "AI_RUNTIME_IDEMPOTENCY_TTL_SECONDS",
)


def _clear_settings_env(monkeypatch: MonkeyPatch) -> None:
    """Remove Settings-related variables so tests do not depend on the host."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_settings_defaults(monkeypatch: MonkeyPatch) -> None:
    """Settings uses documented defaults when no env vars are set."""
    _clear_settings_env(monkeypatch)
    settings = Settings()
    assert settings.app_name == "AI Runtime"
    assert settings.environment is Environment.LOCAL
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.openai_api_key == ""
    assert settings.openai_base_url == "https://api.openai.com/v1"
    assert settings.database_url == "postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.rate_limit_requests_per_minute == 60
    assert settings.rate_limit_burst == 60
    assert settings.idempotency_ttl_seconds == 86400


def test_settings_override_from_environment(monkeypatch: MonkeyPatch) -> None:
    """AI_RUNTIME_ prefixed environment variables override Settings fields."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_RUNTIME_APP_NAME", "Custom Runtime")
    monkeypatch.setenv("AI_RUNTIME_ENVIRONMENT", "staging")
    monkeypatch.setenv("AI_RUNTIME_DEBUG", "true")
    settings = Settings()
    assert settings.app_name == "Custom Runtime"
    assert settings.environment is Environment.STAGING
    assert settings.debug is True


def test_settings_log_level_override_from_environment(monkeypatch: MonkeyPatch) -> None:
    """AI_RUNTIME_LOG_LEVEL overrides the default log level."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_RUNTIME_LOG_LEVEL", "debug")
    settings = Settings()
    assert settings.log_level == "debug"


def test_settings_database_url_override_from_environment(monkeypatch: MonkeyPatch) -> None:
    """AI_RUNTIME_DATABASE_URL overrides the default database URL."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv(
        "AI_RUNTIME_DATABASE_URL",
        "postgresql+asyncpg://user:pass@db:5432/runtime",
    )
    settings = Settings()
    assert settings.database_url == "postgresql+asyncpg://user:pass@db:5432/runtime"


def test_settings_rejects_invalid_environment(monkeypatch: MonkeyPatch) -> None:
    """Invalid AI_RUNTIME_ENVIRONMENT values fail validation."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_RUNTIME_ENVIRONMENT", "invalid")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_rejects_non_asyncpg_database_url(monkeypatch: MonkeyPatch) -> None:
    """database_url must use the postgresql+asyncpg scheme."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_RUNTIME_DATABASE_URL", "postgresql://ai_runtime:ai_runtime@localhost:5432/ai_runtime")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_redis_url_override_from_environment(monkeypatch: MonkeyPatch) -> None:
    """AI_RUNTIME_REDIS_URL overrides the default Redis URL."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_RUNTIME_REDIS_URL", "rediss://cache:6379/1")
    settings = Settings()
    assert settings.redis_url == "rediss://cache:6379/1"


def test_settings_rejects_invalid_redis_url(monkeypatch: MonkeyPatch) -> None:
    """redis_url must use redis:// or rediss://."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_RUNTIME_REDIS_URL", "http://localhost:6379/0")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_rejects_non_positive_rate_limit(monkeypatch: MonkeyPatch) -> None:
    """Rate-limit and idempotency integers must be greater than zero."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_RUNTIME_RATE_LIMIT_REQUESTS_PER_MINUTE", "0")
    with pytest.raises(ValidationError):
        Settings()
