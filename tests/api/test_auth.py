"""Bearer API-key authentication tests for protected routes."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from httpx2 import Response
from ai_runtime.api.app import create_app
from ai_runtime.api.dependencies import get_authenticate_api_key, get_create_response
from ai_runtime.api.middleware.request_context import REQUEST_ID_HEADER
from ai_runtime.application.auth.authenticate_api_key import AuthenticateApiKey
from ai_runtime.application.responses.create_response import CreateResponse
from ai_runtime.domain.api_key import ApiKey, ApiKeyStatus
from ai_runtime.domain.generation import GenerationRequest
from ai_runtime.domain.organization import Organization, OrganizationStatus
from ai_runtime.infrastructure.security.api_key_crypto import Argon2ApiKeyHasher
from tests.api.test_responses import FakeModelProvider, _request_body, _success_response

_UNAUTHORIZED_MESSAGE = "Invalid or missing API key."
_FORBIDDEN_MESSAGE = "Organization is suspended."


class FakeOrganizationRepository:
    """In-memory OrganizationRepository for API auth tests."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, Organization] = {}

    async def add(self, organization: Organization) -> Organization:
        self._by_id[organization.id] = organization
        return organization

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        return self._by_id.get(organization_id)

    async def get_by_slug(self, slug: str) -> Organization | None:
        for organization in self._by_id.values():
            if organization.slug == slug:
                return organization
        return None


class FakeApiKeyRepository:
    """In-memory ApiKeyRepository for API auth tests."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, ApiKey] = {}

    async def add(self, api_key: ApiKey) -> ApiKey:
        self._by_id[api_key.id] = api_key
        return api_key

    async def get_by_id(self, api_key_id: UUID) -> ApiKey | None:
        return self._by_id.get(api_key_id)

    async def list_by_organization(self, organization_id: UUID) -> Sequence[ApiKey]:
        return [key for key in self._by_id.values() if key.organization_id == organization_id]

    async def find_by_prefix(self, prefix: str) -> Sequence[ApiKey]:
        return [key for key in self._by_id.values() if key.prefix == prefix]

    async def save(self, api_key: ApiKey) -> ApiKey:
        self._by_id[api_key.id] = api_key
        return api_key


def _assert_error_envelope(response: Response, *, status_code: int, code: str, message: str) -> str:
    assert response.status_code == status_code
    request_id = response.headers[REQUEST_ID_HEADER]
    assert response.json() == {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        },
    }
    return request_id


def _seed(
    *,
    org_status: OrganizationStatus = OrganizationStatus.ACTIVE,
    key_status: ApiKeyStatus = ApiKeyStatus.ACTIVE,
) -> tuple[AuthenticateApiKey, str]:
    organizations = FakeOrganizationRepository()
    api_keys = FakeApiKeyRepository()
    hasher = Argon2ApiKeyHasher()
    now = datetime.now(UTC)
    org = Organization(
        id=uuid4(),
        name="Acme",
        slug="acme",
        status=org_status,
        created_at=now,
        updated_at=now,
    )
    organizations._by_id[org.id] = org
    secret, prefix = hasher.generate_secret()
    revoked_at = now if key_status is ApiKeyStatus.REVOKED else None
    key = ApiKey(
        id=uuid4(),
        organization_id=org.id,
        name="ci",
        prefix=prefix,
        secret_hash=hasher.hash_secret(secret),
        status=key_status,
        created_at=now,
        revoked_at=revoked_at,
        updated_at=now,
    )
    api_keys._by_id[key.id] = key
    return AuthenticateApiKey(api_keys, organizations, hasher), secret


def _client(provider: FakeModelProvider, authenticate: AuthenticateApiKey) -> TestClient:
    app = create_app()

    async def override_create_response() -> CreateResponse:
        return CreateResponse(provider)

    async def override_authenticate() -> AuthenticateApiKey:
        return authenticate

    app.dependency_overrides[get_create_response] = override_create_response
    app.dependency_overrides[get_authenticate_api_key] = override_authenticate
    return TestClient(app)


def test_post_responses_missing_authorization_returns_401() -> None:
    """POST /v1/responses without Authorization returns 401 envelope."""
    authenticate, _secret = _seed()
    client = _client(FakeModelProvider(response=_success_response()), authenticate)
    response = client.post("/v1/responses", json=_request_body())
    _assert_error_envelope(response, status_code=401, code="unauthorized", message=_UNAUTHORIZED_MESSAGE)


def test_post_responses_malformed_authorization_returns_401() -> None:
    """Non-Bearer Authorization schemes return 401."""
    authenticate, _secret = _seed()
    client = _client(FakeModelProvider(response=_success_response()), authenticate)
    response = client.post(
        "/v1/responses",
        json=_request_body(),
        headers={"Authorization": "Basic not-a-bearer"},
    )
    _assert_error_envelope(response, status_code=401, code="unauthorized", message=_UNAUTHORIZED_MESSAGE)


def test_post_responses_invalid_key_returns_401() -> None:
    """Unknown or wrong secret returns the same generic 401."""
    authenticate, secret = _seed()
    client = _client(FakeModelProvider(response=_success_response()), authenticate)
    response = client.post(
        "/v1/responses",
        json=_request_body(),
        headers={"Authorization": f"Bearer {secret}x"},
    )
    _assert_error_envelope(response, status_code=401, code="unauthorized", message=_UNAUTHORIZED_MESSAGE)
    assert secret not in response.text


def test_post_responses_revoked_key_returns_401() -> None:
    """Revoked keys authenticate as unauthorized (not forbidden)."""
    authenticate, secret = _seed(key_status=ApiKeyStatus.REVOKED)
    client = _client(FakeModelProvider(response=_success_response()), authenticate)
    response = client.post(
        "/v1/responses",
        json=_request_body(),
        headers={"Authorization": f"Bearer {secret}"},
    )
    _assert_error_envelope(response, status_code=401, code="unauthorized", message=_UNAUTHORIZED_MESSAGE)


def test_post_responses_valid_key_returns_200() -> None:
    """Valid active key allows POST /v1/responses with a faked provider."""
    authenticate, secret = _seed()
    provider = FakeModelProvider(response=_success_response())
    client = _client(provider, authenticate)
    response = client.post(
        "/v1/responses",
        json=_request_body(),
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == "resp_abc"
    assert len(provider.requests) == 1
    assert isinstance(provider.requests[0], GenerationRequest)


def test_post_responses_suspended_org_returns_403() -> None:
    """Suspended organization maps to 403 forbidden."""
    authenticate, secret = _seed(org_status=OrganizationStatus.SUSPENDED)
    client = _client(FakeModelProvider(response=_success_response()), authenticate)
    response = client.post(
        "/v1/responses",
        json=_request_body(),
        headers={"Authorization": f"Bearer {secret}"},
    )
    _assert_error_envelope(response, status_code=403, code="forbidden", message=_FORBIDDEN_MESSAGE)


def test_health_remains_unauthenticated() -> None:
    """GET /health stays public and does not require an API key."""
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200


def test_post_responses_openapi_documents_auth_errors() -> None:
    """OpenAPI documents 401 and 403 for POST /v1/responses."""
    schema = create_app().openapi()
    responses: dict[str, Any] = schema["paths"]["/v1/responses"]["post"]["responses"]
    assert "401" in responses
    assert "403" in responses


def test_auth_failure_does_not_echo_secret() -> None:
    """Auth failure bodies must not leak the presented secret."""
    authenticate, secret = _seed()
    client = _client(FakeModelProvider(response=_success_response()), authenticate)
    response = client.post(
        "/v1/responses",
        json=_request_body(),
        headers={"Authorization": f"Bearer {secret}tampered"},
    )
    assert response.status_code == 401
    assert secret not in response.text
    assert "tampered" not in response.text
