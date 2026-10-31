"""IngestSemanticChunk use case tests."""

import asyncio
from datetime import UTC, datetime
import pytest
from uuid import uuid4
from ai_runtime.application.semantic.index_semantic_chunk import IndexSemanticChunk
from ai_runtime.application.semantic.ingest_semantic_chunk import IngestSemanticChunk, IngestSemanticChunkCommand
from ai_runtime.domain.embedding import EmbeddingRequest, EmbeddingResponse, EmbeddingUsage, EmbeddingVector
from ai_runtime.domain.organization import Organization, OrganizationStatus
from ai_runtime.domain.routing import UnsupportedModelError
from ai_runtime.domain.semantic_retrieval import DEFAULT_EMBEDDING_DIMENSIONS
from ai_runtime.application.routing.model_router import ProviderNotRegisteredError
from tests.application.semantic.test_index_and_search import FakeOrganizationRepository, FakeSemanticRetrievalRepository


def _embedding(*, first: float = 1.0) -> tuple[float, ...]:
    values = [0.0] * DEFAULT_EMBEDDING_DIMENSIONS
    values[0] = first
    return tuple(values)


class FakeEmbeddingProvider:
    def __init__(self, *, vector: tuple[float, ...] | None = None) -> None:
        self.requests: list[EmbeddingRequest] = []
        self._vector = vector or _embedding()

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self.requests.append(request)
        return EmbeddingResponse(
            id="emb_test",
            model=request.model,
            data=(EmbeddingVector(index=0, values=self._vector),),
            usage=EmbeddingUsage(input_tokens=2),
        )


def _ingest(
    embedder: FakeEmbeddingProvider,
    chunks: FakeSemanticRetrievalRepository,
    organizations: FakeOrganizationRepository,
) -> IngestSemanticChunk:
    return IngestSemanticChunk({"openai": embedder}, IndexSemanticChunk(chunks, organizations))


def test_ingest_embeds_content_and_persists_chunk() -> None:
    """Ingestion calls the embedding provider then stores the chunk for the organization."""
    embedder = FakeEmbeddingProvider(vector=_embedding(first=0.7))
    chunks = FakeSemanticRetrievalRepository()
    organizations = FakeOrganizationRepository()
    org_id = uuid4()
    now = datetime.now(UTC)
    asyncio.run(
        organizations.add(
            Organization(
                id=org_id,
                slug="acme",
                name="Acme",
                status=OrganizationStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
    )
    ingest = _ingest(embedder, chunks, organizations)
    stored = asyncio.run(
        ingest.execute(
            IngestSemanticChunkCommand(
                organization_id=org_id,
                content="Deploy with Docker Compose.",
            )
        )
    )
    assert stored.organization_id == org_id
    assert stored.content == "Deploy with Docker Compose."
    assert stored.embedding[0] == 0.7
    assert len(chunks.chunks) == 1
    assert embedder.requests[0].input == ("Deploy with Docker Compose.",)


def test_ingest_unknown_embedding_model_raises() -> None:
    """Models outside the catalog raise UnsupportedModelError."""
    ingest = _ingest(FakeEmbeddingProvider(), FakeSemanticRetrievalRepository(), FakeOrganizationRepository())
    with pytest.raises(UnsupportedModelError):
        asyncio.run(
            ingest.execute(
                IngestSemanticChunkCommand(
                    organization_id=uuid4(),
                    content="text",
                    embedding_model="unknown-embed",
                )
            )
        )


def test_ingest_missing_provider_raises() -> None:
    """Missing provider registration surfaces ProviderNotRegisteredError."""
    ingest = IngestSemanticChunk({}, IndexSemanticChunk(FakeSemanticRetrievalRepository(), FakeOrganizationRepository()))
    with pytest.raises(ProviderNotRegisteredError):
        asyncio.run(ingest.execute(IngestSemanticChunkCommand(organization_id=uuid4(), content="text")))
