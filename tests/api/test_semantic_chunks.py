"""POST /v1/semantic_chunks endpoint tests."""

from typing import Any
import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from ai_runtime.api.app import create_app
from ai_runtime.api.dependencies import get_authenticated_principal, get_ingest_semantic_chunk
from ai_runtime.application.auth.authenticate_api_key import AuthenticatedPrincipal
from ai_runtime.application.semantic.index_semantic_chunk import IndexSemanticChunk
from ai_runtime.application.semantic.ingest_semantic_chunk import IngestSemanticChunk
from ai_runtime.domain.generation import MessageRole
from ai_runtime.domain.organization import Organization, OrganizationStatus
from ai_runtime.domain.semantic_retrieval import DEFAULT_EMBEDDING_DIMENSIONS
from tests.api.test_rag_responses import FakeEmbeddingProvider, RecordingAugmentMessagesWithRag, _client_with_rag
from tests.api.test_responses import FakeModelProvider, _fake_principal, _request_body, _success_response
from tests.application.semantic.fakes import override_ingest_semantic_chunk
from tests.application.semantic.test_index_and_search import FakeOrganizationRepository, FakeSemanticRetrievalRepository


def _embedding(*, first: float = 1.0) -> tuple[float, ...]:
    values = [0.0] * DEFAULT_EMBEDDING_DIMENSIONS
    values[0] = first
    return tuple(values)


def _seed_organization(organizations: FakeOrganizationRepository, org_id: UUID) -> None:
    now = datetime.now(UTC)
    asyncio.run(
        organizations.add(
            Organization(
                id=org_id,
                slug="test-org",
                name="Test Org",
                status=OrganizationStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
    )


def _client_with_ingest(
    ingest: IngestSemanticChunk,
    *,
    principal: AuthenticatedPrincipal | None = None,
) -> TestClient:
    app = create_app()
    auth_principal = principal or _fake_principal()

    async def override_principal() -> AuthenticatedPrincipal:
        return auth_principal

    app.dependency_overrides[get_ingest_semantic_chunk] = override_ingest_semantic_chunk(ingest)
    app.dependency_overrides[get_authenticated_principal] = override_principal
    return TestClient(app)


def test_post_semantic_chunks_stores_chunk_for_tenant() -> None:
    """Authenticated ingest returns chunk metadata without echoing content."""
    embedder = FakeEmbeddingProvider()
    chunks = FakeSemanticRetrievalRepository()
    organizations = FakeOrganizationRepository()
    principal = _fake_principal()
    _seed_organization(organizations, principal.organization_id)
    ingest = IngestSemanticChunk({"openai": embedder}, IndexSemanticChunk(chunks, organizations))
    client = _client_with_ingest(ingest, principal=principal)
    response = client.post(
        "/v1/semantic_chunks",
        json={"content": "Run migrations before starting the API."},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["organization_id"] == str(principal.organization_id)
    assert "content" not in body
    assert len(chunks.chunks) == 1
    assert chunks.chunks[0].content == "Run migrations before starting the API."


def test_post_semantic_chunks_unknown_embedding_model_returns_400() -> None:
    """Unknown embedding models map to unsupported_model."""
    principal = _fake_principal()
    organizations = FakeOrganizationRepository()
    _seed_organization(organizations, principal.organization_id)
    ingest = IngestSemanticChunk(
        {"openai": FakeEmbeddingProvider()},
        IndexSemanticChunk(FakeSemanticRetrievalRepository(), organizations),
    )
    client = _client_with_ingest(ingest, principal=principal)
    response = client.post(
        "/v1/semantic_chunks",
        json={"content": "text", "embedding_model": "no-such-embed"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_model"


def test_post_semantic_chunks_missing_embedding_provider_returns_503() -> None:
    """Unconfigured embedding providers return provider_error."""
    principal = _fake_principal()
    organizations = FakeOrganizationRepository()
    _seed_organization(organizations, principal.organization_id)
    ingest = IngestSemanticChunk({}, IndexSemanticChunk(FakeSemanticRetrievalRepository(), organizations))
    client = _client_with_ingest(ingest, principal=principal)
    response = client.post("/v1/semantic_chunks", json={"content": "text"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_error"


def test_ingested_chunk_is_retrieved_by_rag_for_same_organization() -> None:
    """Ingest then RAG on /v1/responses surfaces stored knowledge for the same tenant."""
    embedder = FakeEmbeddingProvider(vector=_embedding(first=0.9))
    chunks = FakeSemanticRetrievalRepository()
    organizations = FakeOrganizationRepository()
    principal = _fake_principal()
    _seed_organization(organizations, principal.organization_id)
    ingest = IngestSemanticChunk({"openai": embedder}, IndexSemanticChunk(chunks, organizations))
    ingest_client = _client_with_ingest(ingest, principal=principal)
    assert ingest_client.post("/v1/semantic_chunks", json={"content": "Use alembic upgrade head."}).status_code == 201

    provider = FakeModelProvider(response=_success_response())
    augment = RecordingAugmentMessagesWithRag(embedder, chunks)
    rag_client = _client_with_rag(provider, augment, principal=principal)
    response = rag_client.post(
        "/v1/responses",
        json=_request_body(rag={"enabled": True, "query": "migrations"}),
    )
    assert response.status_code == 200
    assert provider.requests[0].messages[0].role is MessageRole.SYSTEM
    assert "Use alembic upgrade head." in provider.requests[0].messages[0].content


def test_semantic_chunk_content_is_never_logged(capfd: Any) -> None:
    """Ingest bodies must not appear in structured request logs."""
    embedder = FakeEmbeddingProvider()
    chunks = FakeSemanticRetrievalRepository()
    organizations = FakeOrganizationRepository()
    principal = _fake_principal()
    _seed_organization(organizations, principal.organization_id)
    ingest = IngestSemanticChunk({"openai": embedder}, IndexSemanticChunk(chunks, organizations))
    client = _client_with_ingest(ingest, principal=principal)
    client.post("/v1/semantic_chunks", json={"content": "TOP-SECRET-CHUNK-BODY"})
    captured = capfd.readouterr()
    assert "request_completed" in captured.out + captured.err
    assert "TOP-SECRET-CHUNK-BODY" not in captured.out + captured.err


def test_ingested_chunks_are_isolated_between_organizations() -> None:
    """Org B cannot retrieve org A chunks through RAG."""
    shared_chunks = FakeSemanticRetrievalRepository()
    embedder = FakeEmbeddingProvider(vector=_embedding(first=0.9))
    owner_id = uuid4()
    intruder_id = uuid4()
    organizations = FakeOrganizationRepository()
    _seed_organization(organizations, owner_id)
    _seed_organization(organizations, intruder_id)
    ingest = IngestSemanticChunk({"openai": embedder}, IndexSemanticChunk(shared_chunks, organizations))
    owner = AuthenticatedPrincipal(
        api_key_id=uuid4(),
        organization_id=owner_id,
        organization_slug="owner",
        api_key_prefix="airt_owner1234",
    )
    intruder = AuthenticatedPrincipal(
        api_key_id=uuid4(),
        organization_id=intruder_id,
        organization_slug="intruder",
        api_key_prefix="airt_intr1234",
    )
    owner_client = _client_with_ingest(ingest, principal=owner)
    assert owner_client.post("/v1/semantic_chunks", json={"content": "Owner secret doc."}).status_code == 201

    provider = FakeModelProvider(response=_success_response())
    augment = RecordingAugmentMessagesWithRag(embedder, shared_chunks)
    intruder_client = _client_with_rag(provider, augment, principal=intruder)
    response = intruder_client.post(
        "/v1/responses",
        json=_request_body(rag={"enabled": True, "query": "secret"}),
    )
    assert response.status_code == 200
    system_messages = [item for item in provider.requests[0].messages if item.role is MessageRole.SYSTEM]
    assert not any("Owner secret doc." in item.content for item in system_messages)
