"""Operator-only organization and API key route tests."""

from uuid import UUID
from fastapi.testclient import TestClient
from ai_runtime.api.app import create_app
from ai_runtime.api.dependencies import (
    get_authenticate_api_key,
    get_create_api_key,
    get_create_organization,
    get_list_api_keys,
    get_organization,
    get_revoke_api_key,
    get_rotate_api_key,
)
from ai_runtime.application.api_keys.create_api_key import CreateApiKey
from ai_runtime.application.api_keys.list_api_keys import ListApiKeysForOrganization
from ai_runtime.application.api_keys.revoke_api_key import RevokeApiKey
from ai_runtime.application.api_keys.rotate_api_key import RotateApiKey
from ai_runtime.application.auth.authenticate_api_key import AuthenticateApiKey
from ai_runtime.application.organizations.create_organization import CreateOrganization
from ai_runtime.application.organizations.get_organization import GetOrganization
from ai_runtime.config.settings import Settings
from ai_runtime.domain.api_key import ApiKeyStatus
from ai_runtime.domain.audit import AuditEvent
from ai_runtime.infrastructure.security.api_key_crypto import Argon2ApiKeyHasher
from tests.api.test_auth import FakeApiKeyRepository, FakeOrganizationRepository, _seed

_OPERATOR_TOKEN = "operator-test-token"
_FORBIDDEN_MESSAGE = "This endpoint is restricted to platform operators."
_OPERATOR_UNAUTHORIZED_MESSAGE = "Invalid or missing operator credentials."


class FakeAuditRepository:
    """In-memory AuditRepository for operator route tests."""

    def __init__(self) -> None:
        self.added: list[AuditEvent] = []

    async def add(self, event: AuditEvent) -> AuditEvent:
        self.added.append(event)
        return event

    async def get_by_id(self, event_id: UUID) -> AuditEvent | None:
        return next((event for event in self.added if event.id == event_id), None)


def _operator_client(
    *,
    operator_token: str = _OPERATOR_TOKEN,
    authenticate: AuthenticateApiKey | None = None,
) -> tuple[TestClient, FakeOrganizationRepository, FakeApiKeyRepository, FakeAuditRepository]:
    """Test client with in-memory operator use cases."""
    settings = Settings(
        operator_token=operator_token,
        database_url="postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime",
    )
    app = create_app(settings)
    organizations = FakeOrganizationRepository()
    api_keys = FakeApiKeyRepository()
    audit = FakeAuditRepository()
    hasher = Argon2ApiKeyHasher()

    async def override_create_organization() -> CreateOrganization:
        return CreateOrganization(organizations)

    async def override_get_organization() -> GetOrganization:
        return GetOrganization(organizations)

    async def override_create_api_key() -> CreateApiKey:
        return CreateApiKey(api_keys, organizations, hasher, audit)

    async def override_list_api_keys() -> ListApiKeysForOrganization:
        return ListApiKeysForOrganization(api_keys, organizations)

    async def override_revoke_api_key() -> RevokeApiKey:
        return RevokeApiKey(api_keys, audit)

    async def override_rotate_api_key() -> RotateApiKey:
        return RotateApiKey(api_keys, hasher, audit)

    app.dependency_overrides[get_create_organization] = override_create_organization
    app.dependency_overrides[get_organization] = override_get_organization
    app.dependency_overrides[get_create_api_key] = override_create_api_key
    app.dependency_overrides[get_list_api_keys] = override_list_api_keys
    app.dependency_overrides[get_revoke_api_key] = override_revoke_api_key
    app.dependency_overrides[get_rotate_api_key] = override_rotate_api_key

    auth = authenticate if authenticate is not None else AuthenticateApiKey(api_keys, organizations, hasher)

    async def override_authenticate() -> AuthenticateApiKey:
        return auth

    app.dependency_overrides[get_authenticate_api_key] = override_authenticate

    return TestClient(app), organizations, api_keys, audit


def _operator_headers(token: str = _OPERATOR_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_operator_organization_and_api_key_happy_path() -> None:
    """Operator token can create orgs, keys, list, rotate, and revoke."""
    client, _organizations, api_keys, _audit = _operator_client()

    created = client.post(
        "/v1/organizations",
        json={"name": "Acme", "slug": "acme"},
        headers=_operator_headers(),
    )
    assert created.status_code == 201
    org_body = created.json()
    organization_id = org_body["id"]
    assert org_body["slug"] == "acme"
    assert org_body["status"] == "active"

    fetched = client.get(f"/v1/organizations/{organization_id}", headers=_operator_headers())
    assert fetched.status_code == 200
    assert fetched.json()["id"] == organization_id

    key_created = client.post(
        "/v1/api_keys",
        json={"organization_id": organization_id, "name": "primary"},
        headers=_operator_headers(),
    )
    assert key_created.status_code == 201
    key_body = key_created.json()
    assert key_body["secret"].startswith("airt_")
    assert "secret_hash" not in key_body
    key_id = key_body["id"]

    listed = client.get(f"/v1/api_keys?organization_id={organization_id}", headers=_operator_headers())
    assert listed.status_code == 200
    listed_keys = listed.json()["api_keys"]
    assert len(listed_keys) == 1
    assert "secret" not in listed_keys[0]

    rotated = client.post(f"/v1/api_keys/{key_id}/rotate", headers=_operator_headers())
    assert rotated.status_code == 201
    new_key_id = rotated.json()["id"]
    assert new_key_id != key_id
    assert rotated.json()["secret"].startswith("airt_")

    stored_old = api_keys._by_id[UUID(key_id)]
    assert stored_old.status is ApiKeyStatus.REVOKED

    revoked = client.delete(f"/v1/api_keys/{new_key_id}", headers=_operator_headers())
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


def test_tenant_api_key_cannot_access_operator_routes() -> None:
    """Valid tenant bearer keys receive 403 on operator endpoints."""
    authenticate, tenant_secret = _seed()
    client, _organizations, _api_keys, _audit = _operator_client(authenticate=authenticate)

    response = client.post(
        "/v1/organizations",
        json={"name": "Acme", "slug": "acme"},
        headers={"Authorization": f"Bearer {tenant_secret}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert response.json()["error"]["message"] == _FORBIDDEN_MESSAGE


def test_operator_routes_return_401_with_operator_message_when_unauthorized() -> None:
    """Missing Authorization on operator routes uses operator-specific 401 text."""
    client, *_rest = _operator_client()
    response = client.post(
        "/v1/organizations",
        json={"name": "Acme", "slug": "acme"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.json()["error"]["message"] == _OPERATOR_UNAUTHORIZED_MESSAGE


def test_operator_token_strips_whitespace_for_digest() -> None:
    """Configured operator token is stripped before constant-time comparison."""
    token = "padded-operator-token"
    client, *_rest = _operator_client(operator_token=f"  {token}  ")
    response = client.post(
        "/v1/organizations",
        json={"name": "Acme", "slug": "acme-whitespace"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201


def test_operator_routes_return_503_when_not_configured() -> None:
    """Empty operator token yields 503 on operator routes."""
    client, *_rest = _operator_client(operator_token="")
    response = client.post(
        "/v1/organizations",
        json={"name": "Acme", "slug": "acme"},
        headers=_operator_headers("anything"),
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_error"
    assert response.json()["error"]["message"] == "Operator API is not configured."

    without_auth = client.post(
        "/v1/organizations",
        json={"name": "Other", "slug": "other"},
    )
    assert without_auth.status_code == 503

    whitespace_only = _operator_client(operator_token="   ")
    client_ws, *_rest_ws = whitespace_only
    assert (
        client_ws.post(
            "/v1/organizations",
            json={"name": "Ws", "slug": "ws"},
            headers=_operator_headers("anything"),
        ).status_code
        == 503
    )
