"""Organization-scoped semantic chunk contracts for vector retrieval."""

from dataclasses import dataclass
from datetime import datetime
import math
from uuid import UUID
from ai_runtime.domain.generation import DomainValidationError

# Initial catalog dimension for stored vectors (OpenAI text-embedding-3-small default).
DEFAULT_EMBEDDING_DIMENSIONS = 1536


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty or blank")


def _validate_embedding(values: tuple[float, ...]) -> None:
    if len(values) != DEFAULT_EMBEDDING_DIMENSIONS:
        raise DomainValidationError(f"embedding must contain exactly {DEFAULT_EMBEDDING_DIMENSIONS} dimensions")
    if any(not math.isfinite(value) for value in values):
        raise DomainValidationError("embedding must contain only finite numbers")


@dataclass(frozen=True, slots=True)
class SemanticChunk:
    """Indexed text and embedding belonging to one organization."""

    id: UUID
    organization_id: UUID
    content: str
    embedding: tuple[float, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank(self.content, "content")
        _validate_embedding(self.embedding)
        if self.created_at.tzinfo is None:
            raise DomainValidationError("created_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SemanticSearchResult:
    """One neighbor returned from vector search."""

    chunk_id: UUID
    content: str
    distance: float

    def __post_init__(self) -> None:
        _require_non_blank(self.content, "content")
        if self.distance < 0:
            raise DomainValidationError("distance must not be negative")


@dataclass(frozen=True, slots=True)
class SemanticSearchQuery:
    """Input for organization-scoped nearest-neighbor search."""

    organization_id: UUID
    query_embedding: tuple[float, ...]
    limit: int = 5

    def __post_init__(self) -> None:
        _validate_embedding(self.query_embedding)
        if self.limit <= 0:
            raise DomainValidationError("limit must be greater than zero")
