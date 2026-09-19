"""SQLAlchemy adapter for the PromptRepository port."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ai_runtime.domain.generation import MessageRole
from ai_runtime.domain.prompt import PromptMessageTemplate, PromptTemplate, PromptVersionConflictError
from ai_runtime.infrastructure.db.models.prompt_template import PromptTemplateRow


def _to_domain(row: PromptTemplateRow) -> PromptTemplate:
    return PromptTemplate(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        version=row.version,
        messages=tuple(PromptMessageTemplate(role=MessageRole(item["role"]), content=item["content"]) for item in row.messages),
        created_at=row.created_at,
    )


class SqlAlchemyPromptRepository:
    """Persist prompt template versions through an async SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_version(self, organization_id: UUID, name: str, messages: Sequence[PromptMessageTemplate]) -> PromptTemplate:
        """Insert the next version of ``name``; a concurrent insert raises ``PromptVersionConflictError``."""
        latest = await self._session.scalar(
            select(func.max(PromptTemplateRow.version)).where(
                PromptTemplateRow.organization_id == organization_id,
                PromptTemplateRow.name == name,
            )
        )
        row = PromptTemplateRow(
            id=uuid4(),
            organization_id=organization_id,
            name=name,
            version=(latest or 0) + 1,
            messages=[{"role": message.role.value, "content": message.content} for message in messages],
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        try:
            await self._session.commit()
        except IntegrityError as err:
            await self._session.rollback()
            raise PromptVersionConflictError() from err
        return _to_domain(row)

    async def get(self, organization_id: UUID, name: str, version: int | None) -> PromptTemplate | None:
        """Return the requested version, or the latest when ``version`` is None."""
        statement = select(PromptTemplateRow).where(
            PromptTemplateRow.organization_id == organization_id,
            PromptTemplateRow.name == name,
        )
        if version is not None:
            statement = statement.where(PromptTemplateRow.version == version)
        row = (await self._session.execute(statement.order_by(PromptTemplateRow.version.desc()).limit(1))).scalar_one_or_none()
        return None if row is None else _to_domain(row)

    async def list_versions(self, organization_id: UUID, name: str) -> tuple[PromptTemplate, ...]:
        """Return every version of ``name`` in ascending order."""
        result = await self._session.execute(
            select(PromptTemplateRow)
            .where(PromptTemplateRow.organization_id == organization_id, PromptTemplateRow.name == name)
            .order_by(PromptTemplateRow.version)
        )
        return tuple(_to_domain(row) for row in result.scalars())
