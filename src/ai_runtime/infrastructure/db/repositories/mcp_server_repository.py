"""SQLAlchemy adapter for the McpServerRepository port."""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ai_runtime.domain.mcp import McpServer, McpServerNameConflictError
from ai_runtime.infrastructure.db.models.mcp_server import McpServerRow


def _to_domain(row: McpServerRow) -> McpServer:
    headers = row.headers if isinstance(row.headers, dict) else {}
    normalized = {str(key): str(value) for key, value in headers.items()}
    return McpServer(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        url=row.url,
        headers=normalized,
        created_at=row.created_at,
    )


class SqlAlchemyMcpServerRepository:
    """Persist MCP server registrations through an async SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, server: McpServer) -> McpServer:
        """Insert a server row; duplicate names raise ``McpServerNameConflictError``."""
        if server.created_at is None:
            raise ValueError("McpServer.created_at is required for persistence")
        row = McpServerRow(
            id=server.id,
            organization_id=server.organization_id,
            name=server.name,
            url=server.url,
            headers=dict(server.headers),
            created_at=server.created_at,
        )
        self._session.add(row)
        try:
            await self._session.commit()
        except IntegrityError as err:
            await self._session.rollback()
            raise McpServerNameConflictError(name=server.name) from err
        return _to_domain(row)

    async def get_by_name(self, organization_id: UUID, name: str) -> McpServer | None:
        """Return one server by organization and name."""
        row = await self._session.scalar(
            select(McpServerRow).where(
                McpServerRow.organization_id == organization_id,
                McpServerRow.name == name,
            )
        )
        return None if row is None else _to_domain(row)

    async def list_by_organization(self, organization_id: UUID) -> list[McpServer]:
        """Return every MCP server registered for the organization."""
        rows = await self._session.scalars(
            select(McpServerRow).where(McpServerRow.organization_id == organization_id).order_by(McpServerRow.name)
        )
        return [_to_domain(row) for row in rows.all()]
