"""FastAPI dependency providers for application use cases."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
import httpx
from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ai_runtime.api.errors import APIError, ErrorCode
from ai_runtime.api.middleware.request_context import get_request_id
from ai_runtime.application.auth.authenticate_api_key import AuthenticateApiKey, AuthenticatedPrincipal
from ai_runtime.application.responses.create_response import CreateResponse
from ai_runtime.config.settings import Settings
from ai_runtime.domain.api_key import InvalidApiKeyCredentialsError
from ai_runtime.domain.organization import OrganizationSuspendedError
from ai_runtime.infrastructure.db import create_db_engine, create_session_factory
from ai_runtime.infrastructure.db.repositories.api_key_repository import SqlAlchemyApiKeyRepository
from ai_runtime.infrastructure.db.repositories.organization_repository import SqlAlchemyOrganizationRepository
from ai_runtime.infrastructure.db.repositories.usage_repository import SqlAlchemyUsageRepository
from ai_runtime.infrastructure.pricing import StaticCostEstimator
from ai_runtime.infrastructure.security.api_key_crypto import Argon2ApiKeyHasher
from ai_runtime.providers.openai.adapter import OpenAIModelProvider

_UNAUTHORIZED_MESSAGE = "Invalid or missing API key."
_FORBIDDEN_SUSPENDED_MESSAGE = "Organization is suspended."


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


def extract_bearer_token(request: Request) -> str:
    """Extract the bearer secret from the Authorization header.

    Raises ``APIError`` with 401 for missing, blank, or non-Bearer credentials.
    """
    authorization = request.headers.get("Authorization")
    if authorization is None or not authorization.strip():
        raise APIError(code=ErrorCode.UNAUTHORIZED, message=_UNAUTHORIZED_MESSAGE, status_code=401)
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        raise APIError(code=ErrorCode.UNAUTHORIZED, message=_UNAUTHORIZED_MESSAGE, status_code=401)
    return credentials.strip()


async def get_authenticate_api_key(session: DbSessionDep) -> AuthenticateApiKey:
    """Build AuthenticateApiKey with request-scoped SQLAlchemy repositories."""
    return AuthenticateApiKey(
        SqlAlchemyApiKeyRepository(session),
        SqlAlchemyOrganizationRepository(session),
        Argon2ApiKeyHasher(),
    )


AuthenticateApiKeyDep = Annotated[AuthenticateApiKey, Depends(get_authenticate_api_key)]


async def get_authenticated_principal(
    request: Request,
    secret: Annotated[str, Depends(extract_bearer_token)],
    use_case: AuthenticateApiKeyDep,
) -> AuthenticatedPrincipal:
    """Authenticate the bearer secret and attach the principal to request state."""
    try:
        principal = await use_case.execute(secret)
    except InvalidApiKeyCredentialsError as err:
        raise APIError(code=ErrorCode.UNAUTHORIZED, message=_UNAUTHORIZED_MESSAGE, status_code=401) from err
    except OrganizationSuspendedError as err:
        raise APIError(code=ErrorCode.FORBIDDEN, message=_FORBIDDEN_SUSPENDED_MESSAGE, status_code=403) from err
    request.state.principal = principal
    return principal


AuthenticatedPrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)]


async def get_create_response(request: Request, session: DbSessionDep) -> CreateResponse:
    """Build CreateResponse wired to OpenAI, usage persistence, and cost estimation."""
    settings: Settings = request.app.state.settings
    http_client: httpx.AsyncClient = request.app.state.http_client
    provider = OpenAIModelProvider(
        api_key=settings.openai_api_key,
        http_client=http_client,
        base_url=settings.openai_base_url,
    )
    return CreateResponse(
        provider,
        SqlAlchemyUsageRepository(session),
        StaticCostEstimator(),
        provider_name="openai",
    )


CreateResponseDep = Annotated[CreateResponse, Depends(get_create_response)]


def require_request_id(request: Request) -> str:
    """Return the middleware-assigned request_id or raise if missing."""
    request_id = get_request_id(request)
    if request_id is None or not request_id.strip():
        raise APIError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Request correlation identifier is missing.",
            status_code=500,
        )
    return request_id


RequestIdDep = Annotated[str, Depends(require_request_id)]


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
