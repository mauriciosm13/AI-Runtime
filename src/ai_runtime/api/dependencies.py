"""FastAPI dependency providers for application use cases."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
import httpx
from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ai_runtime.application.responses.create_response import CreateResponse
from ai_runtime.config.settings import Settings
from ai_runtime.infrastructure.db import create_db_engine, create_session_factory
from ai_runtime.providers.openai.adapter import OpenAIModelProvider


def get_settings(request: Request) -> Settings:
    """Return the Settings instance stored on the application."""
    settings = request.app.state.settings
    assert isinstance(settings, Settings)
    return settings


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped SQLAlchemy async session."""
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


async def get_create_response(request: Request) -> CreateResponse:
    """Build CreateResponse wired to the configured OpenAI provider."""
    settings: Settings = request.app.state.settings
    http_client: httpx.AsyncClient = request.app.state.http_client
    provider = OpenAIModelProvider(
        api_key=settings.openai_api_key,
        http_client=http_client,
        base_url=settings.openai_base_url,
    )
    return CreateResponse(provider)


CreateResponseDep = Annotated[CreateResponse, Depends(get_create_response)]


@asynccontextmanager
async def application_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage shared HTTP and database resources for the application lifetime."""
    settings: Settings = app.state.settings
    engine = create_db_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    try:
        async with httpx.AsyncClient() as http_client:
            app.state.http_client = http_client
            yield
    finally:
        await engine.dispose()
