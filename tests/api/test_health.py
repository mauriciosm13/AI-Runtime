"""Health endpoint and application factory tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from ai_runtime.api.app import create_app


def test_create_app_returns_fastapi_instance() -> None:
    """create_app builds a usable FastAPI application."""
    app = create_app()
    assert isinstance(app, FastAPI)


def test_health_returns_ok() -> None:
    """GET /health responds with 200 and the expected liveness payload."""
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_documented_in_openapi() -> None:
    """GET /health appears in the generated OpenAPI schema."""
    schema = create_app().openapi()
    paths = schema["paths"]
    assert "/health" in paths
    assert "get" in paths["/health"]
