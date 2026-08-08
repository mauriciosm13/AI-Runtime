"""Port for loading organization access policy and model entitlements."""

from typing import Protocol, runtime_checkable
from uuid import UUID
from ai_runtime.domain.organization_policy import ModelEntitlement, OrganizationPolicy


@runtime_checkable
class OrganizationPolicyRepository(Protocol):
    """Async contract for organization policy reads."""

    async def get_policy(self, organization_id: UUID) -> OrganizationPolicy:
        """Return policy for ``organization_id``.

        When no persisted policy exists, returns defaults (unlimited quota).
        """
        ...

    async def list_entitlements(self, organization_id: UUID) -> tuple[ModelEntitlement, ...]:
        """Return model entitlements configured for ``organization_id``."""
        ...
