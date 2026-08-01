"""FastAPI application factory."""

from fastapi import FastAPI
from ai_runtime.config.settings import Settings
from ai_runtime.api.routes.health import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure a new FastAPI application instance.

    When ``settings`` is omitted, a fresh ``Settings`` instance is loaded from
    the process environment. Callers may inject an explicit instance in tests
    or alternative entrypoints; no process-wide settings singleton is used.
    """
    resolved = settings if settings is not None else Settings()
    app = FastAPI(
        title=resolved.app_name,
        version="0.1.0",
        debug=resolved.debug,
    )
    app.include_router(health_router)
    return app
