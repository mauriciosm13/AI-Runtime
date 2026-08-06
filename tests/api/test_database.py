"""Database lifespan and session dependency wiring tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from ai_runtime.api.app import create_app
from ai_runtime.api.dependencies import DbSessionDep
from ai_runtime.config.settings import Settings


def _app_from_client(client: TestClient) -> FastAPI:
    assert isinstance(client.app, FastAPI)
    return client.app


def test_lifespan_wires_engine_and_session_factory() -> None:
    """Application lifespan stores an AsyncEngine and session factory on app.state."""
    app = create_app(
        Settings(
            database_url="postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime",
        )
    )
    with TestClient(app) as client:
        wired = _app_from_client(client)
        assert isinstance(wired.state.engine, AsyncEngine)
        assert isinstance(wired.state.session_factory, async_sessionmaker)
        response = client.get("/health")
        assert response.status_code == 200


def test_db_session_dependency_yields_async_session() -> None:
    """get_db_session yields a request-scoped AsyncSession without requiring SQL."""
    app = create_app(
        Settings(
            database_url="postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime",
        )
    )

    @app.get("/_test/db-session")
    async def probe_session(session: DbSessionDep) -> dict[str, str]:
        assert isinstance(session, AsyncSession)
        return {"status": "ok"}

    with TestClient(app) as client:
        response = client.get("/_test/db-session")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_create_app_accepts_injected_settings_database_url() -> None:
    """Injected Settings.database_url is used when creating the engine."""
    database_url = "postgresql+asyncpg://custom:custom@db.example:5432/custom_db"
    app = create_app(Settings(database_url=database_url))
    with TestClient(app) as client:
        engine = _app_from_client(client).state.engine
        assert isinstance(engine, AsyncEngine)
        assert str(engine.url).startswith("postgresql+asyncpg://custom:***@db.example:5432/custom_db")
