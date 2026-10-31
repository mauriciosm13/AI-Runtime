"""Retrieve organization knowledge and inject it into message lists."""

from collections.abc import Mapping
from uuid import UUID
from ai_runtime.application.routing.model_router import ProviderNotRegisteredError
from ai_runtime.application.semantic.search_semantic_chunks import SearchSemanticChunks
from ai_runtime.domain.embedding import EmbeddingRequest
from ai_runtime.domain.embedding_routing import DEFAULT_EMBEDDING_CATALOG, resolve_embedding_route
from ai_runtime.domain.generation import Message
from ai_runtime.domain.rag import RagPolicy, prepend_retrieved_context, resolve_rag_query
from ai_runtime.domain.semantic_retrieval import DEFAULT_EMBEDDING_DIMENSIONS, SemanticSearchQuery
from ai_runtime.ports.embedding_provider import EmbeddingProvider


class AugmentMessagesWithRag:
    """Embed a query, search semantic chunks, and prepend retrieved context."""

    def __init__(
        self,
        providers: Mapping[str, EmbeddingProvider],
        search: SearchSemanticChunks,
        *,
        catalog: Mapping[str, str] | None = None,
    ) -> None:
        self._providers = providers
        self._search = search
        self._catalog = DEFAULT_EMBEDDING_CATALOG if catalog is None else catalog

    async def execute(
        self,
        organization_id: UUID,
        messages: tuple[Message, ...],
        policy: RagPolicy,
    ) -> tuple[Message, ...]:
        """Return ``messages`` augmented with retrieved context when policy is enabled."""
        if not policy.enabled:
            return messages
        query_text = resolve_rag_query(messages, override=policy.query)
        route = resolve_embedding_route(policy.embedding_model, self._catalog)
        provider = self._providers.get(route.provider)
        if provider is None:
            raise ProviderNotRegisteredError(provider=route.provider)
        embedding = await provider.embed(
            EmbeddingRequest(
                model=route.model,
                input=(query_text,),
                dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
            )
        )
        query_vector = embedding.data[0].values
        hits = await self._search.execute(
            SemanticSearchQuery(
                organization_id=organization_id,
                query_embedding=query_vector,
                limit=policy.top_k,
            )
        )
        return prepend_retrieved_context(messages, [hit.content for hit in hits])
