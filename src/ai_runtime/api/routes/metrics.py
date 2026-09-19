"""Operational Prometheus metrics endpoint."""

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics(request: Request) -> str:
    """Return in-process Prometheus text for scrapers."""
    metrics = request.app.state.metrics
    rendered = metrics.render_prometheus()
    assert isinstance(rendered, str)
    return rendered
