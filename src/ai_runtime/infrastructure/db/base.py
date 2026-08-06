"""SQLAlchemy declarative base for ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared metadata root for infrastructure ORM models.

    Business tables are added in later persistence features. Alembic autogenerate
    and migrations target ``Base.metadata``.
    """
