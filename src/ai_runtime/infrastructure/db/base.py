"""SQLAlchemy declarative base for ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared metadata root for infrastructure ORM models.

    Alembic autogenerate and migrations target ``Base.metadata``. Import ORM
    modules (via ``infrastructure.db.models``) so tables register on this base.
    """
