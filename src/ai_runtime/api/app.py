"""FastAPI application factory."""

from fastapi import FastAPI
from ai_runtime.api.routes.health import router as health_router


def create_app() -> FastAPI:
    """Create and configure a new FastAPI application instance."""
    app = FastAPI(title="AI Runtime", version="0.1.0")
    app.include_router(health_router)
    return app
