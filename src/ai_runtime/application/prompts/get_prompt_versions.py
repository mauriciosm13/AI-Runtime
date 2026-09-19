"""List the versions of an organization prompt template."""

from uuid import UUID
from ai_runtime.domain.prompt import PromptNotFoundError, PromptTemplate, validate_prompt_name
from ai_runtime.ports.prompt_repository import PromptRepository


class GetPromptVersions:
    """Load every version of ``name`` for one organization."""

    def __init__(self, repository: PromptRepository) -> None:
        self._repository = repository

    async def execute(self, organization_id: UUID, name: str) -> tuple[PromptTemplate, ...]:
        """Return versions in ascending order; raise ``PromptNotFoundError`` when none exist."""
        validate_prompt_name(name)
        versions = await self._repository.list_versions(organization_id, name)
        if not versions:
            raise PromptNotFoundError(name=name, version=None)
        return versions
