"""GET /metrics operational endpoint tests."""

from fastapi.testclient import TestClient
from ai_runtime.api.app import create_app


def test_metrics_is_unauthenticated_prometheus_text() -> None:
    """GET /metrics returns Prometheus text after a request and does not require auth."""
    client = TestClient(create_app())
    health = client.get("/health")
    assert health.status_code == 200
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "http_requests_total" in response.text
    assert "/health" in response.text


def test_metrics_is_documented_in_openapi() -> None:
    """GET /metrics appears in the generated OpenAPI schema."""
    schema = create_app().openapi()
    assert "/metrics" in schema["paths"]
    assert "get" in schema["paths"]["/metrics"]
