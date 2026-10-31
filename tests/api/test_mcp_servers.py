"""MCP server registration and discovery endpoints."""

from datetime import UTC, datetime
from uuid import uuid4
import asyncio
from fastapi.testclient import TestClient
from ai_runtime.api.app import create_app
from ai_runtime.api.dependencies import get_authenticated_principal, get_list_mcp_server_tools, get_list_mcp_servers, get_register_mcp_server
from ai_runtime.application.auth.authenticate_api_key import AuthenticatedPrincipal
from ai_runtime.application.mcp.list_mcp_server_tools import ListMcpServerTools
from ai_runtime.application.mcp.list_mcp_servers import ListMcpServers
from ai_runtime.application.mcp.register_mcp_server import RegisterMcpServer
from ai_runtime.domain.generation import ToolDefinition
from ai_runtime.domain.mcp import McpServer
from tests.api.test_responses import _fake_principal
from tests.application.mcp.fakes import FakeMcpServerRepository, FakeMcpToolClient


def _client(
    repository: FakeMcpServerRepository,
    client: FakeMcpToolClient,
    *,
    principal: AuthenticatedPrincipal | None = None,
) -> TestClient:
    app = create_app()
    auth_principal = principal or _fake_principal()

    async def override_principal() -> AuthenticatedPrincipal:
        return auth_principal

    async def override_register() -> RegisterMcpServer:
        return RegisterMcpServer(repository)

    async def override_list() -> ListMcpServers:
        return ListMcpServers(repository)

    async def override_list_tools() -> ListMcpServerTools:
        return ListMcpServerTools(repository, client)

    app.dependency_overrides[get_register_mcp_server] = override_register
    app.dependency_overrides[get_list_mcp_servers] = override_list
    app.dependency_overrides[get_list_mcp_server_tools] = override_list_tools
    app.dependency_overrides[get_authenticated_principal] = override_principal
    return TestClient(app)


def test_register_and_list_mcp_servers() -> None:
    """Tenants can register MCP servers and list metadata without secrets."""
    principal = _fake_principal()
    repository = FakeMcpServerRepository()
    http = _client(repository, FakeMcpToolClient(), principal=principal)
    created = http.post(
        "/v1/mcp_servers",
        json={"name": "crm", "url": "https://mcp.example/rpc", "headers": {"Authorization": "Bearer x"}},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "crm"
    assert body["organization_id"] == str(principal.organization_id)
    assert "url" not in body
    assert "headers" not in body
    listed = http.get("/v1/mcp_servers")
    assert listed.status_code == 200
    assert listed.json()["servers"][0]["name"] == "crm"


def test_list_mcp_server_tools_returns_namespaced_tools() -> None:
    """GET tools returns namespaced definitions from the MCP client."""
    principal = _fake_principal()
    repository = FakeMcpServerRepository()
    asyncio.run(
        repository.add(
            McpServer(
                id=uuid4(),
                organization_id=principal.organization_id,
                name="crm",
                url="https://mcp.example/rpc",
                created_at=datetime.now(UTC),
            )
        )
    )
    mcp_client = FakeMcpToolClient((ToolDefinition(name="search", description="d", parameters={"type": "object"}),))
    http = _client(repository, mcp_client, principal=principal)
    response = http.get("/v1/mcp_servers/crm/tools")
    assert response.status_code == 200
    assert response.json()["tools"][0]["name"] == "crm.search"


def test_mcp_servers_are_isolated_between_organizations() -> None:
    """Org B cannot list org A MCP servers."""
    shared = FakeMcpServerRepository()
    owner = _fake_principal()
    intruder = AuthenticatedPrincipal(
        api_key_id=uuid4(),
        organization_id=uuid4(),
        organization_slug="other",
        api_key_prefix="airt_other1234",
    )
    owner_client = _client(shared, FakeMcpToolClient(), principal=owner)
    assert owner_client.post("/v1/mcp_servers", json={"name": "crm", "url": "https://mcp.example/rpc"}).status_code == 201
    intruder_client = _client(shared, FakeMcpToolClient(), principal=intruder)
    assert intruder_client.get("/v1/mcp_servers").json()["servers"] == []
