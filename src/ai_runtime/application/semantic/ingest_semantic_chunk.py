"""Use case for embedding and indexing organization-scoped semantic chunks."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID
from ai_runtime.application.routing.model_router import ProviderNotRegisteredError
from ai_runtime.application.semantic.index_semantic_chunk import IndexSemanticChunk, IndexSemanticChunkCommand
from ai_runtime.domain.embedding import EmbeddingRequest
from ai_runtime.domain.embedding_routing import DEFAULT_EMBEDDING_CATALOG, DEFAULT_RAG_EMBEDDING_MODEL, resolve_embedding_route
from ai_runtime.domain.semantic_retrieval import DEFAULT_EMBEDDING_DIMENSIONS, SemanticChunk
from ai_runtime.ports.embedding_provider import EmbeddingProvider


@dataclass(frozen=True, slots=True)
class IngestSemanticChunkCommand:
    """Input for HTTP semantic chunk ingestion."""

    organization_id: UUID
    content: str
    embedding_model: str = DEFAULT_RAG_EMBEDDING_MODEL


class IngestSemanticChunk:
    """Embed client content and persist it as an organization-scoped chunk."""

    def __init__(
        self,
        providers: Mapping[str, EmbeddingProvider],
        index: IndexSemanticChunk,
        *,
        catalog: Mapping[str, str] | None = None,
    ) -> None:
        self._providers = providers
        self._index = index
        self._catalog = DEFAULT_EMBEDDING_CATALOG if catalog is None else catalog

    async def execute(self, command: IngestSemanticChunkCommand) -> SemanticChunk:
        route = resolve_embedding_route(command.embedding_model, self._catalog)
        provider = self._providers.get(route.provider)
        if provider is None:
            raise ProviderNotRegisteredError(provider=route.provider)
        embedding = await provider.embed(
            EmbeddingRequest(
                model=route.model,
                input=(command.content,),
                dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
            )
        )
        vector = embedding.data[0].values
        return await self._index.execute(
            IndexSemanticChunkCommand(
                organization_id=command.organization_id,
                content=command.content,
                embedding=vector,
            )
        )
