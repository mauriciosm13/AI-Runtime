"""Use case for indexing an organization-scoped semantic chunk."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.domain.organization import OrganizationNotFoundError
from ai_runtime.domain.semantic_retrieval import SemanticChunk
from ai_runtime.ports.organization_repository import OrganizationRepository
from ai_runtime.ports.semantic_retrieval_repository import SemanticRetrievalRepository


@dataclass(frozen=True, slots=True)
class IndexSemanticChunkCommand:
    """Input for storing one semantic chunk."""

    organization_id: UUID
    content: str
    embedding: tuple[float, ...]


class IndexSemanticChunk:
    """Persist a chunk after verifying the organization exists."""

    def __init__(
        self,
        chunks: SemanticRetrievalRepository,
        organizations: OrganizationRepository,
    ) -> None:
        self._chunks = chunks
        self._organizations = organizations

    async def execute(self, command: IndexSemanticChunkCommand) -> SemanticChunk:
        organization = await self._organizations.get_by_id(command.organization_id)
        if organization is None:
            raise OrganizationNotFoundError(f"organization not found: {command.organization_id}")

        now = datetime.now(UTC)
        chunk = SemanticChunk(
            id=uuid4(),
            organization_id=command.organization_id,
            content=command.content,
            embedding=command.embedding,
            created_at=now,
        )
        return await self._chunks.add(chunk)
