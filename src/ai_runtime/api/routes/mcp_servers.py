"""Organization-scoped MCP server registration and tool discovery."""

from typing import Annotated
from fastapi import APIRouter, Depends
from ai_runtime.api.dependencies import AuthenticatedPrincipalDep, get_list_mcp_server_tools, get_list_mcp_servers, get_register_mcp_server
from ai_runtime.api.schemas.errors import ErrorResponseSchema
from ai_runtime.api.schemas.mcp_servers import CreateMcpServerRequest, McpServerCreatedSchema, McpServerListSchema
from ai_runtime.api.schemas.mcp_servers import McpServerSummarySchema, McpToolListSchema
from ai_runtime.application.mcp.list_mcp_server_tools import ListMcpServerTools
from ai_runtime.application.mcp.list_mcp_servers import ListMcpServers
from ai_runtime.application.mcp.register_mcp_server import RegisterMcpServer

router = APIRouter(tags=["mcp_servers"])


@router.post(
    "/mcp_servers",
    status_code=201,
    responses={
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid API key"},
        409: {"model": ErrorResponseSchema, "description": "Duplicate server name"},
        422: {"model": ErrorResponseSchema, "description": "Invalid request"},
    },
)
async def post_mcp_servers(
    body: CreateMcpServerRequest,
    principal: AuthenticatedPrincipalDep,
    use_case: Annotated[RegisterMcpServer, Depends(get_register_mcp_server)],
) -> McpServerCreatedSchema:
    """Register a remote MCP tool server for the caller's organization."""
    server = await use_case.execute(
        principal.organization_id,
        body.name,
        body.url,
        body.headers,
    )
    return McpServerCreatedSchema.from_domain(server)


@router.get(
    "/mcp_servers",
    responses={401: {"model": ErrorResponseSchema, "description": "Missing or invalid API key"}},
)
async def get_mcp_servers(
    principal: AuthenticatedPrincipalDep,
    use_case: Annotated[ListMcpServers, Depends(get_list_mcp_servers)],
) -> McpServerListSchema:
    """List MCP servers registered for the caller's organization."""
    summaries = await use_case.execute(principal.organization_id)
    return McpServerListSchema(servers=[McpServerSummarySchema.from_domain(item) for item in summaries])


@router.get(
    "/mcp_servers/{name}/tools",
    responses={
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid API key"},
        404: {"model": ErrorResponseSchema, "description": "MCP server not found"},
        502: {"model": ErrorResponseSchema, "description": "MCP discovery failed"},
    },
)
async def get_mcp_server_tools(
    name: str,
    principal: AuthenticatedPrincipalDep,
    use_case: Annotated[ListMcpServerTools, Depends(get_list_mcp_server_tools)],
) -> McpToolListSchema:
    """Discover tools from a registered MCP server."""
    tools = await use_case.execute(principal.organization_id, name)
    return McpToolListSchema(
        tools=[{"name": tool.name, "description": tool.description, "parameters": tool.parameters} for tool in tools]
    )
