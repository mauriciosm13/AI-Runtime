"""Health endpoint and application factory tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from ai_runtime.api.app import create_app
from ai_runtime.config.settings import Environment, Settings


def test_create_app_returns_fastapi_instance() -> None:
    """create_app builds a usable FastAPI application without arguments."""
    app = create_app()
    assert isinstance(app, FastAPI)


def test_create_app_applies_injected_settings() -> None:
    """Injected Settings control FastAPI title and debug mode."""
    settings = Settings(
        app_name="Injected Runtime",
        environment=Environment.DEVELOPMENT,
        debug=True,
    )
    app = create_app(settings=settings)
    assert app.title == "Injected Runtime"
    assert app.debug is True


def test_health_returns_ok() -> None:
    """GET /health responds with 200 and the expected liveness payload."""
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_rejects_non_get_methods() -> None:
    """POST /health is rejected because liveness is a read-only probe."""
    client = TestClient(create_app())
    response = client.post("/health")
    assert response.status_code == 405


def test_health_does_not_require_database_connectivity() -> None:
    """Liveness succeeds without querying the database, even with an unreachable DSN."""
    app = create_app(
        Settings(
            database_url="postgresql+asyncpg://ai_runtime:ai_runtime@127.0.0.1:1/ai_runtime",
        )
    )
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_health_is_documented_in_openapi() -> None:
    """GET /health appears in the generated OpenAPI schema."""
    schema = create_app().openapi()
    paths = schema["paths"]
    assert "/health" in paths
    assert "get" in paths["/health"]
