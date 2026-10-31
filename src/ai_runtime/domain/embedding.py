"""Provider-neutral embedding contracts."""

from dataclasses import dataclass
import math
from ai_runtime.domain.generation import DomainValidationError


def _require_non_blank(value: str, field_name: str) -> None:
    """Reject empty or whitespace-only strings."""
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty or blank")


@dataclass(frozen=True, slots=True)
class EmbeddingUsage:
    """Token accounting for an embedding call."""

    input_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0:
            raise DomainValidationError("input_tokens must not be negative")


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    """One embedding vector aligned with an input text index."""

    index: int
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.index < 0:
            raise DomainValidationError("index must not be negative")
        if not self.values:
            raise DomainValidationError("values must contain at least one dimension")
        if any(not math.isfinite(value) for value in self.values):
            raise DomainValidationError("values must contain only finite numbers")


@dataclass(frozen=True, slots=True)
class EmbeddingRequest:
    """A provider-neutral request to embed one or more text inputs."""

    model: str
    input: tuple[str, ...]
    dimensions: int | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.model, "model")
        if not self.input:
            raise DomainValidationError("input must contain at least one text value")
        for position, text in enumerate(self.input):
            _require_non_blank(text, f"input[{position}]")
        if self.dimensions is not None and self.dimensions <= 0:
            raise DomainValidationError("dimensions must be greater than zero")


@dataclass(frozen=True, slots=True)
class EmbeddingResponse:
    """A provider-neutral embedding result."""

    id: str
    model: str
    data: tuple[EmbeddingVector, ...]
    usage: EmbeddingUsage

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.model, "model")
        if not self.data:
            raise DomainValidationError("data must contain at least one embedding vector")
        indices = [item.index for item in self.data]
        if len(set(indices)) != len(indices):
            raise DomainValidationError("data indices must be unique")
        if sorted(indices) != list(range(len(self.data))):
            raise DomainValidationError("data indices must be contiguous starting at zero")
