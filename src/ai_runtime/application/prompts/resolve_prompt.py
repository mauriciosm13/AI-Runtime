"""Resolve a prompt reference into rendered messages."""

from uuid import UUID
from ai_runtime.domain.generation import Message
from ai_runtime.domain.prompt import PromptNotFoundError, PromptReference
from ai_runtime.ports.prompt_repository import PromptRepository


class ResolvePrompt:
    """Load an organization's template and render it with the caller's variables."""

    def __init__(self, repository: PromptRepository) -> None:
        self._repository = repository

    async def execute(self, organization_id: UUID, reference: PromptReference) -> tuple[Message, ...]:
        """Return rendered messages.

        Raises ``PromptNotFoundError`` when the template is absent for this
        organization and ``DomainValidationError`` on a variable mismatch.
        """
        template = await self._repository.get(organization_id, reference.name, reference.version)
        if template is None:
            raise PromptNotFoundError(name=reference.name, version=reference.version)
        return template.render(reference.variables)
