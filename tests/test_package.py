"""Packaging smoke tests."""

import ai_runtime


def test_package_is_importable() -> None:
    """The installed distribution exposes the application package."""
    assert ai_runtime.__doc__ is not None
