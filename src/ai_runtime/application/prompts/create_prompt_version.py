"""Create the next immutable version of an organization prompt template."""

from collections.abc import Sequence
from uuid import UUID
from ai_runtime.domain.prompt import PromptMessageTemplate, PromptTemplate, validate_prompt_name
from ai_runtime.domain.generation import DomainValidationError
from ai_runtime.ports.prompt_repository import PromptRepository


class CreatePromptVersion:
    """Validate a template and persist it as the next version of ``name``."""

    def __init__(self, repository: PromptRepository) -> None:
        self._repository = repository

    async def execute(self, organization_id: UUID, name: str, messages: Sequence[PromptMessageTemplate]) -> PromptTemplate:
        """Return the newly created version."""
        validate_prompt_name(name)
        if not messages:
            raise DomainValidationError("messages must contain at least one message")
        return await self._repository.create_version(organization_id, name, messages)
