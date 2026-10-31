"""POST /v1/responses RAG integration tests."""

from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from ai_runtime.api.app import create_app
from ai_runtime.api.dependencies import get_augment_messages_with_rag, get_authenticated_principal, get_create_response, get_resolve_prompt, get_resolve_tools_for_generation
from ai_runtime.application.auth.authenticate_api_key import AuthenticatedPrincipal
from ai_runtime.application.policy.enforce_organization_policy import EnforceOrganizationPolicy
from ai_runtime.application.rag.augment_messages_with_rag import AugmentMessagesWithRag
from ai_runtime.application.resilience.provider_executor import ProviderExecutor
from ai_runtime.application.responses.create_response import CreateResponse
from ai_runtime.application.routing.model_router import ModelRouter
from ai_runtime.application.semantic.search_semantic_chunks import SearchSemanticChunks
from ai_runtime.domain.embedding import EmbeddingRequest, EmbeddingResponse, EmbeddingUsage, EmbeddingVector
from ai_runtime.domain.generation import MessageRole
from ai_runtime.domain.semantic_retrieval import DEFAULT_EMBEDDING_DIMENSIONS, SemanticSearchResult
from tests.api.test_responses import FakeModelProvider, _fake_principal, _request_body, _success_response
from tests.application.policy.test_enforce_organization_policy import FakeOrganizationPolicyRepository
from tests.application.responses.test_create_response import FakeAuditRepository, FakeCostEstimator, FakeIdempotencyStore
from tests.application.responses.test_create_response import FakeMetrics, FakeRateLimiter, FakeResponseCache, FakeUsageRepository
from tests.application.prompts.fakes import FakePromptRepository, override_resolve_prompt
from tests.application.mcp.fakes import override_resolve_tools_for_generation
from tests.application.rag.fakes import override_augment_messages_with_rag
from tests.application.semantic.test_index_and_search import FakeSemanticRetrievalRepository


def _embedding(*, first: float = 1.0) -> tuple[float, ...]:
    values = [0.0] * DEFAULT_EMBEDDING_DIMENSIONS
    values[0] = first
    return tuple(values)


class FakeEmbeddingProvider:
    def __init__(self, *, vector: tuple[float, ...] | None = None) -> None:
        self.requests: list[EmbeddingRequest] = []
        self._vector = vector or _embedding()

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self.requests.append(request)
        return EmbeddingResponse(
            id="emb_test",
            model=request.model,
            data=(EmbeddingVector(index=0, values=self._vector),),
            usage=EmbeddingUsage(input_tokens=1),
        )


class RecordingAugmentMessagesWithRag(AugmentMessagesWithRag):
    """Augment use case wired to test doubles."""

    def __init__(self, embedder: FakeEmbeddingProvider, chunks: FakeSemanticRetrievalRepository) -> None:
        super().__init__({"openai": embedder}, SearchSemanticChunks(chunks))
        self.embedder = embedder


def _client_with_rag(
    provider: FakeModelProvider,
    augment: AugmentMessagesWithRag,
    *,
    principal: AuthenticatedPrincipal | None = None,
) -> TestClient:
    app = create_app()
    auth_principal = principal or _fake_principal()
    records = FakeUsageRepository()

    async def override_create_response() -> CreateResponse:
        policies = FakeOrganizationPolicyRepository()
        return CreateResponse(
            ProviderExecutor(
                ModelRouter(providers={"openai": provider}),
                max_retries=0,
                retry_base_delay_seconds=0,
                failover_enabled=False,
            ),
            records,
            FakeCostEstimator(),
            FakeRateLimiter(),
            FakeIdempotencyStore(),
            EnforceOrganizationPolicy(policies, records),
            FakeResponseCache(),
            FakeMetrics(),
            FakeAuditRepository(),
        )

    async def override_principal() -> AuthenticatedPrincipal:
        return auth_principal

    app.dependency_overrides[get_create_response] = override_create_response
    app.dependency_overrides[get_augment_messages_with_rag] = override_augment_messages_with_rag(augment)
    app.dependency_overrides[get_resolve_tools_for_generation] = override_resolve_tools_for_generation()
    app.dependency_overrides[get_authenticated_principal] = override_principal
    app.dependency_overrides[get_resolve_prompt] = override_resolve_prompt(FakePromptRepository())
    return TestClient(app)


def test_post_responses_injects_rag_context_before_generation() -> None:
    """rag.enabled prepends retrieved chunks to messages forwarded to the provider."""
    embedder = FakeEmbeddingProvider()
    principal = _fake_principal()
    chunk_id = uuid4()

    class ScopedChunks(FakeSemanticRetrievalRepository):
        async def search(
            self,
            organization_id: UUID,
            query_embedding: tuple[float, ...],
            *,
            limit: int,
        ) -> list[SemanticSearchResult]:
            assert organization_id == principal.organization_id
            assert limit == 2
            return [SemanticSearchResult(chunk_id=chunk_id, content="Runbook step 1", distance=0.1)]

    augment = RecordingAugmentMessagesWithRag(embedder, ScopedChunks())
    provider = FakeModelProvider(response=_success_response())
    client = _client_with_rag(provider, augment, principal=principal)

    response = client.post(
        "/v1/responses",
        json=_request_body(rag={"enabled": True, "top_k": 2, "query": "how to deploy"}),
    )
    assert response.status_code == 200
    assert len(provider.requests) == 1
    messages = provider.requests[0].messages
    assert messages[0].role is MessageRole.SYSTEM
    assert "Runbook step 1" in messages[0].content
    assert messages[1].role is MessageRole.USER
    assert embedder.requests[0].input == ("how to deploy",)


def test_post_responses_without_rag_unchanged() -> None:
    """Requests without rag match pre-RAG message forwarding."""
    embedder = FakeEmbeddingProvider()
    augment = RecordingAugmentMessagesWithRag(embedder, FakeSemanticRetrievalRepository())
    provider = FakeModelProvider(response=_success_response())
    client = _client_with_rag(provider, augment)
    response = client.post("/v1/responses", json=_request_body())
    assert response.status_code == 200
    assert len(provider.requests[0].messages) == 1
    assert embedder.requests == []


def test_post_responses_rag_unknown_embedding_model_returns_400() -> None:
    """Unknown embedding models map to unsupported_model."""
    augment = RecordingAugmentMessagesWithRag(FakeEmbeddingProvider(), FakeSemanticRetrievalRepository())
    provider = FakeModelProvider(response=_success_response())
    client = _client_with_rag(provider, augment)
    response = client.post(
        "/v1/responses",
        json=_request_body(rag={"enabled": True, "embedding_model": "no-such-embed"}),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_model"


def test_post_responses_rag_missing_embedding_provider_returns_503() -> None:
    """When OpenAI embeddings are not registered, RAG fails with provider_error."""
    augment = AugmentMessagesWithRag({}, SearchSemanticChunks(FakeSemanticRetrievalRepository()))
    provider = FakeModelProvider(response=_success_response())
    app = create_app()
    records = FakeUsageRepository()

    async def override_create_response() -> CreateResponse:
        policies = FakeOrganizationPolicyRepository()
        return CreateResponse(
            ProviderExecutor(
                ModelRouter(providers={"openai": provider}),
                max_retries=0,
                retry_base_delay_seconds=0,
                failover_enabled=False,
            ),
            records,
            FakeCostEstimator(),
            FakeRateLimiter(),
            FakeIdempotencyStore(),
            EnforceOrganizationPolicy(policies, records),
            FakeResponseCache(),
            FakeMetrics(),
            FakeAuditRepository(),
        )

    async def override_principal() -> AuthenticatedPrincipal:
        return _fake_principal()

    app.dependency_overrides[get_create_response] = override_create_response
    app.dependency_overrides[get_augment_messages_with_rag] = override_augment_messages_with_rag(augment)
    app.dependency_overrides[get_resolve_tools_for_generation] = override_resolve_tools_for_generation()
    app.dependency_overrides[get_authenticated_principal] = override_principal
    app.dependency_overrides[get_resolve_prompt] = override_resolve_prompt(FakePromptRepository())
    client = TestClient(app)
    response = client.post("/v1/responses", json=_request_body(rag={"enabled": True}))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_error"
