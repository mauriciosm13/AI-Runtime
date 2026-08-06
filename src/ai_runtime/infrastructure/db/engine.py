"""Async SQLAlchemy engine and session-factory construction."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_db_engine(database_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine for the given PostgreSQL URL.

    The engine is created eagerly but does not open connections until first use.
    """
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to ``engine`` for request-scoped sessions."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
