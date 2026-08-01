"""Settings loading and validation tests."""

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch
from ai_runtime.config.settings import Environment, Settings

_SETTINGS_ENV_VARS = (
    "AI_RUNTIME_APP_NAME",
    "AI_RUNTIME_ENVIRONMENT",
    "AI_RUNTIME_DEBUG",
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


def test_settings_rejects_invalid_environment(monkeypatch: MonkeyPatch) -> None:
    """Invalid AI_RUNTIME_ENVIRONMENT values fail validation."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_RUNTIME_ENVIRONMENT", "invalid")
    with pytest.raises(ValidationError):
        Settings()
