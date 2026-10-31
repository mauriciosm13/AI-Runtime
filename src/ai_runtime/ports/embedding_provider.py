"""Port for invoking embedding models against a provider."""

from typing import Protocol, runtime_checkable
from ai_runtime.domain.embedding import EmbeddingRequest, EmbeddingResponse


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Async contract that provider adapters must satisfy for embeddings."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Return embedding vectors for the given provider-neutral request."""
        ...
