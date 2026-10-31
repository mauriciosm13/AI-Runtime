"""Test doubles for RAG dependency overrides."""

from collections.abc import Awaitable, Callable
from ai_runtime.application.rag.augment_messages_with_rag import AugmentMessagesWithRag
from ai_runtime.application.semantic.search_semantic_chunks import SearchSemanticChunks
from tests.application.semantic.test_index_and_search import FakeSemanticRetrievalRepository


def noop_augment_messages_with_rag() -> AugmentMessagesWithRag:
    """Build an augment use case that never calls real DB or embedding HTTP."""
    return AugmentMessagesWithRag({}, SearchSemanticChunks(FakeSemanticRetrievalRepository()))


def override_augment_messages_with_rag(
    augment: AugmentMessagesWithRag | None = None,
) -> Callable[[], Awaitable[AugmentMessagesWithRag]]:
    """FastAPI override factory for ``get_augment_messages_with_rag``."""

    async def _override() -> AugmentMessagesWithRag:
        return noop_augment_messages_with_rag() if augment is None else augment

    return _override
