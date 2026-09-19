"""Port for persisting and loading organization prompt templates."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID
from ai_runtime.domain.prompt import PromptMessageTemplate, PromptTemplate


@runtime_checkable
class PromptRepository(Protocol):
    """Async contract for organization-scoped prompt template storage."""

    async def create_version(self, organization_id: UUID, name: str, messages: Sequence[PromptMessageTemplate]) -> PromptTemplate:
        """Persist the next immutable version of ``name`` and return it.

        Raises ``PromptVersionConflictError`` when a concurrent writer took the version.
        """
        ...

    async def get(self, organization_id: UUID, name: str, version: int | None) -> PromptTemplate | None:
        """Return the requested version, the latest when ``version`` is None, or None when absent."""
        ...

    async def list_versions(self, organization_id: UUID, name: str) -> tuple[PromptTemplate, ...]:
        """Return all versions of ``name`` ordered by ascending version."""
        ...
