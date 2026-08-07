"""SQLAlchemy adapter for the OrganizationRepository port."""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ai_runtime.domain.organization import Organization, OrganizationSlugConflictError, OrganizationStatus
from ai_runtime.infrastructure.db.models.organization import OrganizationRow


def _to_domain(row: OrganizationRow) -> Organization:
    """Map an ORM row to the domain Organization entity."""
    return Organization(
        id=row.id,
        name=row.name,
        slug=row.slug,
        status=OrganizationStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_row(organization: Organization) -> OrganizationRow:
    """Map a domain Organization to an ORM row."""
    return OrganizationRow(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        status=organization.status.value,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


class SqlAlchemyOrganizationRepository:
    """Persist and load organizations through an async SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, organization: Organization) -> Organization:
        """Insert ``organization`` and commit the current transaction."""
        row = _to_row(organization)
        self._session.add(row)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise OrganizationSlugConflictError(f"organization slug already exists: {organization.slug}") from exc
        await self._session.refresh(row)
        return _to_domain(row)

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        """Load an organization by primary key."""
        row = await self._session.get(OrganizationRow, organization_id)
        if row is None:
            return None
        return _to_domain(row)

    async def get_by_slug(self, slug: str) -> Organization | None:
        """Load an organization by unique slug."""
        result = await self._session.execute(select(OrganizationRow).where(OrganizationRow.slug == slug))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_domain(row)
