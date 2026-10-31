"""POST /v1/responses with MCP tool discovery."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4
from fastapi.testclient import TestClient
from ai_runtime.api.app import create_app
from ai_runtime.api.dependencies import get_augment_messages_with_rag, get_authenticated_principal, get_create_response
from ai_runtime.api.dependencies import get_resolve_prompt, get_resolve_tools_for_generation
from ai_runtime.application.auth.authenticate_api_key import AuthenticatedPrincipal
from ai_runtime.application.policy.enforce_organization_policy import EnforceOrganizationPolicy
from ai_runtime.application.resilience.provider_executor import ProviderExecutor
from ai_runtime.application.responses.create_response import CreateResponse
from ai_runtime.application.routing.model_router import ModelRouter
from ai_runtime.domain.generation import ToolDefinition
from ai_runtime.domain.mcp import McpServer
from tests.api.test_responses import FakeModelProvider, _fake_principal, _request_body, _success_response
from tests.application.mcp.fakes import FakeMcpServerRepository, FakeMcpToolClient, PassthroughResolveTools
from tests.application.policy.test_enforce_organization_policy import FakeOrganizationPolicyRepository
from tests.application.prompts.fakes import FakePromptRepository, override_resolve_prompt
from tests.application.rag.fakes import override_augment_messages_with_rag
from tests.application.responses.test_create_response import FakeAuditRepository, FakeCostEstimator, FakeIdempotencyStore
from tests.application.responses.test_create_response import FakeMetrics, FakeRateLimiter, FakeResponseCache, FakeUsageRepository


def _client_with_mcp(
    provider: FakeModelProvider,
    resolver: PassthroughResolveTools,
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
    app.dependency_overrides[get_authenticated_principal] = override_principal
    async def override_resolve_tools() -> PassthroughResolveTools:
        return resolver

    app.dependency_overrides[get_resolve_tools_for_generation] = override_resolve_tools
    app.dependency_overrides[get_augment_messages_with_rag] = override_augment_messages_with_rag()
    app.dependency_overrides[get_resolve_prompt] = override_resolve_prompt(FakePromptRepository())
    return TestClient(app)


def test_post_responses_merges_mcp_tools_before_generation() -> None:
    """mcp.servers forwards discovered tools to the provider."""
    principal = _fake_principal()
    org_id = principal.organization_id
    now = datetime.now(UTC)
    repository = FakeMcpServerRepository()
    asyncio.run(
        repository.add(
            McpServer(
                id=uuid4(),
                organization_id=org_id,
                name="crm",
                url="https://mcp.example/rpc",
                created_at=now,
            )
        )
    )
    client_tools = FakeMcpToolClient((ToolDefinition(name="lookup", description="Find", parameters={"type": "object"}),))
    resolver = PassthroughResolveTools(repository, client_tools)
    provider = FakeModelProvider(response=_success_response())
    client = _client_with_mcp(provider, resolver, principal=principal)
    body = _request_body(mcp={"servers": ["crm"]})
    response = client.post("/v1/responses", json=body)
    assert response.status_code == 200
    assert provider.requests[0].tools[0].name == "crm.lookup"


def test_post_responses_mcp_unknown_server_returns_404() -> None:
    """Unknown MCP server names return mcp_server_not_found."""
    resolver = PassthroughResolveTools(FakeMcpServerRepository(), FakeMcpToolClient())
    provider = FakeModelProvider(response=_success_response())
    client = _client_with_mcp(provider, resolver)
    body = _request_body(mcp={"servers": ["missing"]})
    response = client.post("/v1/responses", json=body)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "mcp_server_not_found"
