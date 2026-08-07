"""SQLAlchemy adapter for the ApiKeyRepository port."""

from collections.abc import Sequence
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ai_runtime.domain.api_key import ApiKey, ApiKeyStatus
from ai_runtime.infrastructure.db.models.api_key import ApiKeyRow


def _to_domain(row: ApiKeyRow) -> ApiKey:
    """Map an ORM row to the domain ApiKey entity."""
    return ApiKey(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        prefix=row.prefix,
        secret_hash=row.secret_hash,
        status=ApiKeyStatus(row.status),
        created_at=row.created_at,
        revoked_at=row.revoked_at,
        updated_at=row.updated_at,
    )


def _to_row(api_key: ApiKey) -> ApiKeyRow:
    """Map a domain ApiKey to an ORM row."""
    return ApiKeyRow(
        id=api_key.id,
        organization_id=api_key.organization_id,
        name=api_key.name,
        prefix=api_key.prefix,
        secret_hash=api_key.secret_hash,
        status=api_key.status.value,
        created_at=api_key.created_at,
        revoked_at=api_key.revoked_at,
        updated_at=api_key.updated_at,
    )


class SqlAlchemyApiKeyRepository:
    """Persist and load API keys through an async SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, api_key: ApiKey) -> ApiKey:
        """Insert ``api_key`` and commit the current transaction."""
        row = _to_row(api_key)
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _to_domain(row)

    async def get_by_id(self, api_key_id: UUID) -> ApiKey | None:
        """Load an API key by primary key."""
        row = await self._session.get(ApiKeyRow, api_key_id)
        if row is None:
            return None
        return _to_domain(row)

    async def list_by_organization(self, organization_id: UUID) -> Sequence[ApiKey]:
        """Load API keys for an organization, newest first."""
        result = await self._session.execute(
            select(ApiKeyRow).where(ApiKeyRow.organization_id == organization_id).order_by(ApiKeyRow.created_at.desc())
        )
        return [_to_domain(row) for row in result.scalars().all()]

    async def find_by_prefix(self, prefix: str) -> Sequence[ApiKey]:
        """Load API keys matching a non-secret display prefix."""
        result = await self._session.execute(select(ApiKeyRow).where(ApiKeyRow.prefix == prefix))
        return [_to_domain(row) for row in result.scalars().all()]

    async def save(self, api_key: ApiKey) -> ApiKey:
        """Update an existing API key row and commit."""
        row = await self._session.get(ApiKeyRow, api_key.id)
        if row is None:
            raise LookupError(f"api key not found for save: {api_key.id}")
        row.organization_id = api_key.organization_id
        row.name = api_key.name
        row.prefix = api_key.prefix
        row.secret_hash = api_key.secret_hash
        row.status = api_key.status.value
        row.created_at = api_key.created_at
        row.revoked_at = api_key.revoked_at
        row.updated_at = api_key.updated_at
        await self._session.commit()
        await self._session.refresh(row)
        return _to_domain(row)
