"""RAG policy and message augmentation helpers."""

from dataclasses import dataclass
from collections.abc import Sequence
from ai_runtime.domain.embedding_routing import DEFAULT_RAG_EMBEDDING_MODEL
from ai_runtime.domain.generation import DomainValidationError, Message, MessageRole

DEFAULT_RAG_TOP_K = 5
MAX_RAG_TOP_K = 20

_RETRIEVED_CONTEXT_HEADER = "Retrieved context (organization knowledge):"


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty or blank")


@dataclass(frozen=True, slots=True)
class RagPolicy:
    """Client-selected retrieval settings for one generation request."""

    enabled: bool = False
    query: str | None = None
    top_k: int = DEFAULT_RAG_TOP_K
    embedding_model: str = DEFAULT_RAG_EMBEDDING_MODEL

    def __post_init__(self) -> None:
        _require_non_blank(self.embedding_model, "embedding_model")
        if self.top_k <= 0:
            raise DomainValidationError("top_k must be greater than zero")
        if self.top_k > MAX_RAG_TOP_K:
            raise DomainValidationError(f"top_k must not exceed {MAX_RAG_TOP_K}")
        if self.query is not None:
            _require_non_blank(self.query, "query")


def resolve_rag_query(messages: Sequence[Message], *, override: str | None) -> str:
    """Return the explicit query or the last non-empty user message."""
    if override is not None:
        return override.strip()
    for message in reversed(messages):
        if message.role is MessageRole.USER and message.content.strip():
            return message.content.strip()
    raise DomainValidationError("rag requires a non-empty user message or an explicit query")


def format_retrieved_context(chunks: Sequence[str]) -> str:
    """Build the system message body for retrieved organization knowledge."""
    if not chunks:
        return ""
    numbered = "\n".join(f"{index}. {content}" for index, content in enumerate(chunks, start=1))
    return f"{_RETRIEVED_CONTEXT_HEADER}\n\n{numbered}"


def prepend_retrieved_context(messages: tuple[Message, ...], chunks: Sequence[str]) -> tuple[Message, ...]:
    """Prepend a system message when retrieval returned content."""
    body = format_retrieved_context(chunks)
    if not body:
        return messages
    return (Message(role=MessageRole.SYSTEM, content=body), *messages)
