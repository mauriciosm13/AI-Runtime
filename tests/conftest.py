"""Pytest configuration and shared fixtures."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Fail fast with setup guidance when the package is not installed."""
    try:
        import ai_runtime  # noqa: F401
    except ModuleNotFoundError:
        pytest.exit(
            "ai_runtime is not installed. From the repository root, run: pip install -e '.[dev]'",
            returncode=1,
        )
