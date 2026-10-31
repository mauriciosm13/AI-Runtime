"""Unit tests for provider-neutral embedding domain contracts."""

import pytest
from ai_runtime.domain.embedding import (
    DomainValidationError,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)


def test_valid_embedding_request_and_response() -> None:
    """Valid request and response construct cleanly."""
    request = EmbeddingRequest(model="text-embedding-test", input=("hello", "world"))
    usage = EmbeddingUsage(input_tokens=4)
    response = EmbeddingResponse(
        id="emb_1",
        model="text-embedding-test",
        data=(
            EmbeddingVector(index=0, values=(0.1, 0.2)),
            EmbeddingVector(index=1, values=(0.3, 0.4)),
        ),
        usage=usage,
    )
    assert request.model == "text-embedding-test"
    assert request.input == ("hello", "world")
    assert request.dimensions is None
    assert response.usage.input_tokens == 4


def test_rejects_blank_model() -> None:
    """Empty model names are rejected."""
    with pytest.raises(DomainValidationError, match="model"):
        EmbeddingRequest(model="  ", input=("hello",))


def test_rejects_empty_input() -> None:
    """EmbeddingRequest must include at least one input string."""
    with pytest.raises(DomainValidationError, match="input"):
        EmbeddingRequest(model="text-embedding-test", input=())


def test_rejects_blank_input_text() -> None:
    """Each input string must be non-blank."""
    with pytest.raises(DomainValidationError, match="input\\[1\\]"):
        EmbeddingRequest(model="text-embedding-test", input=("ok", "   "))


def test_rejects_invalid_dimensions() -> None:
    """dimensions, when provided, must be positive."""
    with pytest.raises(DomainValidationError, match="dimensions"):
        EmbeddingRequest(model="text-embedding-test", input=("hello",), dimensions=0)


def test_rejects_non_finite_vector_values() -> None:
    """Embedding vectors must contain finite floats only."""
    with pytest.raises(DomainValidationError, match="finite"):
        EmbeddingVector(index=0, values=(float("nan"), 1.0))


def test_rejects_duplicate_or_non_contiguous_indices() -> None:
    """Response data indices must be unique and contiguous from zero."""
    usage = EmbeddingUsage(input_tokens=1)
    with pytest.raises(DomainValidationError, match="unique"):
        EmbeddingResponse(
            id="emb_1",
            model="text-embedding-test",
            data=(
                EmbeddingVector(index=0, values=(0.1,)),
                EmbeddingVector(index=0, values=(0.2,)),
            ),
            usage=usage,
        )
    with pytest.raises(DomainValidationError, match="contiguous"):
        EmbeddingResponse(
            id="emb_1",
            model="text-embedding-test",
            data=(EmbeddingVector(index=1, values=(0.1,)),),
            usage=usage,
        )
