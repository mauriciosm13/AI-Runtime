"""Unit tests for in-process Prometheus metrics."""

from ai_runtime.telemetry.metrics import InProcessMetrics


def test_render_prometheus_includes_counter_and_summary() -> None:
    """Counters and observed samples render as Prometheus text."""
    metrics = InProcessMetrics()
    metrics.increment("http_requests_total", {"method": "GET", "path": "/health", "status": "200"})
    metrics.observe("http_request_duration_seconds", 0.01, {"method": "GET", "path": "/health"})
    text = metrics.render_prometheus()
    assert "http_requests_total{" in text
    assert 'method="GET"' in text
    assert "http_request_duration_seconds_sum" in text
    assert "http_request_duration_seconds_count" in text
