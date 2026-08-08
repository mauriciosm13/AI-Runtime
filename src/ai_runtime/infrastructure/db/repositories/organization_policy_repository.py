"""SQLAlchemy adapter for the OrganizationPolicyRepository port."""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ai_runtime.domain.organization_policy import ModelEntitlement, OrganizationPolicy
from ai_runtime.infrastructure.db.models.organization_policy import OrganizationModelEntitlementRow, OrganizationPolicyRow


def _policy_to_domain(row: OrganizationPolicyRow) -> OrganizationPolicy:
    return OrganizationPolicy(
        organization_id=row.organization_id,
        monthly_token_limit=row.monthly_token_limit,
    )


def _entitlement_to_domain(row: OrganizationModelEntitlementRow) -> ModelEntitlement:
    return ModelEntitlement(
        organization_id=row.organization_id,
        model=row.model,
    )


class SqlAlchemyOrganizationPolicyRepository:
    """Load organization policy and entitlements through an async SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_policy(self, organization_id: UUID) -> OrganizationPolicy:
        """Return persisted policy or defaults when none exists."""
        row = await self._session.get(OrganizationPolicyRow, organization_id)
        if row is None:
            return OrganizationPolicy(organization_id=organization_id)
        return _policy_to_domain(row)

    async def list_entitlements(self, organization_id: UUID) -> tuple[ModelEntitlement, ...]:
        """Return all model entitlements for ``organization_id``."""
        result = await self._session.execute(
            select(OrganizationModelEntitlementRow)
            .where(OrganizationModelEntitlementRow.organization_id == organization_id)
            .order_by(OrganizationModelEntitlementRow.model)
        )
        return tuple(_entitlement_to_domain(row) for row in result.scalars())
