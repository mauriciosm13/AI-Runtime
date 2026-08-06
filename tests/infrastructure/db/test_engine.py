"""SQLAlchemy engine and session-factory construction tests."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from ai_runtime.infrastructure.db.engine import create_db_engine, create_session_factory

_TEST_DATABASE_URL = "postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime"


def test_create_db_engine_returns_async_engine() -> None:
    """create_db_engine builds an AsyncEngine for a postgresql+asyncpg URL."""
    engine = create_db_engine(_TEST_DATABASE_URL)
    try:
        assert isinstance(engine, AsyncEngine)
        assert engine.url.drivername == "postgresql+asyncpg"
    finally:
        engine.sync_engine.dispose()


def test_create_session_factory_returns_async_sessionmaker() -> None:
    """create_session_factory returns an async_sessionmaker bound to the engine."""
    engine = create_db_engine(_TEST_DATABASE_URL)
    try:
        factory = create_session_factory(engine)
        assert isinstance(factory, async_sessionmaker)
        assert factory.class_ is AsyncSession
        assert factory.kw["expire_on_commit"] is False
    finally:
        engine.sync_engine.dispose()
