"""Shared database URL resolution for Alembic and application settings."""

from ai_runtime.config.settings import Settings


def get_alembic_database_url() -> str:
    """Return the async PostgreSQL URL used by Alembic migrations.

    Uses the same ``Settings`` / ``AI_RUNTIME_DATABASE_URL`` convention as the API.
    """
    return Settings().database_url
