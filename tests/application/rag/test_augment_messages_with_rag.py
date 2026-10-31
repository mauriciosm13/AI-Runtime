"""AugmentMessagesWithRag use case tests."""

import asyncio
from datetime import UTC, datetime
import pytest
from uuid import uuid4
from ai_runtime.application.rag.augment_messages_with_rag import AugmentMessagesWithRag
from ai_runtime.application.semantic.search_semantic_chunks import SearchSemanticChunks
from ai_runtime.domain.embedding import EmbeddingRequest, EmbeddingResponse, EmbeddingUsage, EmbeddingVector
from ai_runtime.domain.generation import DomainValidationError, Message, MessageRole
from ai_runtime.domain.rag import RagPolicy
from ai_runtime.domain.routing import UnsupportedModelError
from ai_runtime.domain.semantic_retrieval import DEFAULT_EMBEDDING_DIMENSIONS, SemanticChunk
from ai_runtime.application.routing.model_router import ProviderNotRegisteredError
from tests.application.semantic.test_index_and_search import FakeSemanticRetrievalRepository


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
            usage=EmbeddingUsage(input_tokens=3),
        )


def _augment(
    embedder: FakeEmbeddingProvider,
    chunks: FakeSemanticRetrievalRepository,
) -> AugmentMessagesWithRag:
    return AugmentMessagesWithRag({"openai": embedder}, SearchSemanticChunks(chunks))


def test_augment_prepends_system_message_with_retrieved_chunks() -> None:
    """Enabled RAG prepends numbered organization context before existing messages."""
    embedder = FakeEmbeddingProvider()
    chunks = FakeSemanticRetrievalRepository()
    org_id = uuid4()
    now = datetime.now(UTC)
    asyncio.run(
        chunks.add(
            SemanticChunk(
                id=uuid4(),
                organization_id=org_id,
                content="Policy A",
                embedding=_embedding(first=0.5),
                created_at=now,
            )
        )
    )
    messages = (Message(role=MessageRole.USER, content="What is our policy?"),)
    policy = RagPolicy(enabled=True, top_k=3)
    result = asyncio.run(_augment(embedder, chunks).execute(org_id, messages, policy))
    assert len(result) == 2
    assert result[0].role is MessageRole.SYSTEM
    assert "Retrieved context (organization knowledge):" in result[0].content
    assert "1. Policy A" in result[0].content
    assert result[1] == messages[0]
    assert embedder.requests[0].input == ("What is our policy?",)


def test_augment_uses_explicit_query_override() -> None:
    """An explicit rag.query is embedded instead of the last user message."""
    embedder = FakeEmbeddingProvider()
    chunks = FakeSemanticRetrievalRepository()
    org_id = uuid4()
    messages = (Message(role=MessageRole.USER, content="ignored"),)
    policy = RagPolicy(enabled=True, query="search this")
    asyncio.run(_augment(embedder, chunks).execute(org_id, messages, policy))
    assert embedder.requests[0].input == ("search this",)


def test_augment_skips_system_message_when_no_hits() -> None:
    """Empty retrieval leaves the message list unchanged."""
    embedder = FakeEmbeddingProvider()
    chunks = FakeSemanticRetrievalRepository()
    org_id = uuid4()
    messages = (Message(role=MessageRole.USER, content="Hello"),)
    policy = RagPolicy(enabled=True)
    result = asyncio.run(_augment(embedder, chunks).execute(org_id, messages, policy))
    assert result == messages


def test_augment_disabled_returns_messages_unchanged() -> None:
    """Disabled policy is a no-op without touching providers."""
    embedder = FakeEmbeddingProvider()
    chunks = FakeSemanticRetrievalRepository()
    messages = (Message(role=MessageRole.USER, content="Hello"),)
    policy = RagPolicy(enabled=False)
    result = asyncio.run(_augment(embedder, chunks).execute(uuid4(), messages, policy))
    assert result == messages
    assert embedder.requests == []


def test_augment_rejects_unknown_embedding_model() -> None:
    """Models outside the catalog raise UnsupportedModelError."""
    embedder = FakeEmbeddingProvider()
    chunks = FakeSemanticRetrievalRepository()
    policy = RagPolicy(enabled=True, embedding_model="unknown-embed")
    with pytest.raises(UnsupportedModelError):
        asyncio.run(
            _augment(embedder, chunks).execute(
                uuid4(),
                (Message(role=MessageRole.USER, content="Hi"),),
                policy,
            )
        )


def test_augment_raises_when_embedding_provider_missing() -> None:
    """Missing provider registration surfaces ProviderNotRegisteredError."""
    augment = AugmentMessagesWithRag({}, SearchSemanticChunks(FakeSemanticRetrievalRepository()))
    policy = RagPolicy(enabled=True)
    with pytest.raises(ProviderNotRegisteredError):
        asyncio.run(
            augment.execute(
                uuid4(),
                (Message(role=MessageRole.USER, content="Hi"),),
                policy,
            )
        )


def test_augment_requires_user_message_or_query() -> None:
    """RAG without query override needs a non-empty user message."""
    embedder = FakeEmbeddingProvider()
    chunks = FakeSemanticRetrievalRepository()
    policy = RagPolicy(enabled=True)
    with pytest.raises(DomainValidationError):
        asyncio.run(
            _augment(embedder, chunks).execute(
                uuid4(),
                (Message(role=MessageRole.ASSISTANT, content="Hi"),),
                policy,
            )
        )
