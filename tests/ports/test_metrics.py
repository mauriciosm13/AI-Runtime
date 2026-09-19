"""Unit tests for the Metrics port contract."""

from ai_runtime.ports.metrics import Metrics
from ai_runtime.telemetry.metrics import InProcessMetrics


def test_in_process_metrics_satisfies_contract() -> None:
    """InProcessMetrics is accepted as Metrics."""
    metrics: Metrics = InProcessMetrics()
    assert isinstance(metrics, Metrics)
    metrics.increment("http_requests_total")
    metrics.observe("http_request_duration_seconds", 0.1)
