"""Port for persisting and loading API keys."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID
from ai_runtime.domain.api_key import ApiKey


@runtime_checkable
class ApiKeyRepository(Protocol):
    """Async persistence contract for API key credentials."""

    async def add(self, api_key: ApiKey) -> ApiKey:
        """Persist a new API key and return the stored entity."""
        ...

    async def get_by_id(self, api_key_id: UUID) -> ApiKey | None:
        """Return the API key with ``api_key_id``, or ``None``."""
        ...

    async def list_by_organization(self, organization_id: UUID) -> Sequence[ApiKey]:
        """Return API keys belonging to ``organization_id`` (newest first)."""
        ...

    async def find_by_prefix(self, prefix: str) -> Sequence[ApiKey]:
        """Return keys whose non-secret display prefix matches ``prefix``.

        Intended for future bearer auth lookup (#14): resolve candidates by
        prefix, then verify the full secret against ``secret_hash``.
        """
        ...

    async def save(self, api_key: ApiKey) -> ApiKey:
        """Persist updates to an existing API key (e.g. revoke)."""
        ...
