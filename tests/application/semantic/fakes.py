"""Test doubles for semantic chunk dependency overrides."""

from collections.abc import Awaitable, Callable
from ai_runtime.application.semantic.index_semantic_chunk import IndexSemanticChunk
from ai_runtime.application.semantic.ingest_semantic_chunk import IngestSemanticChunk
from tests.application.semantic.test_index_and_search import FakeOrganizationRepository, FakeSemanticRetrievalRepository


def noop_ingest_semantic_chunk() -> IngestSemanticChunk:
    """Build an ingest use case that never calls real DB or embedding HTTP."""
    chunks = FakeSemanticRetrievalRepository()
    organizations = FakeOrganizationRepository()
    return IngestSemanticChunk({}, IndexSemanticChunk(chunks, organizations))


def override_ingest_semantic_chunk(
    ingest: IngestSemanticChunk | None = None,
) -> Callable[[], Awaitable[IngestSemanticChunk]]:
    """FastAPI override factory for ``get_ingest_semantic_chunk``."""

    async def _override() -> IngestSemanticChunk:
        return noop_ingest_semantic_chunk() if ingest is None else ingest

    return _override
