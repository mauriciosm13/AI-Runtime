"""Provider-neutral generation contracts for text model invocations."""

from dataclasses import dataclass
from enum import StrEnum


class DomainValidationError(ValueError):
    """Raised when generation domain data violates an invariant."""


class MessageRole(StrEnum):
    """Roles recognized in a generation conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


def _require_non_blank(value: str, field_name: str) -> None:
    """Reject empty or whitespace-only strings."""
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty or blank")


@dataclass(frozen=True, slots=True)
class Message:
    """A single conversation message with a role and textual content."""

    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        _require_non_blank(self.content, "content")


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """A provider-neutral request to generate model output."""

    model: str
    messages: tuple[Message, ...]
    temperature: float | None = None
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.model, "model")
        if not self.messages:
            raise DomainValidationError("messages must contain at least one message")
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise DomainValidationError("temperature must be between 0 and 2 inclusive")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise DomainValidationError("max_output_tokens must be greater than zero")


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Token accounting for a generation call."""

    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0:
            raise DomainValidationError("input_tokens must not be negative")
        if self.output_tokens < 0:
            raise DomainValidationError("output_tokens must not be negative")

    @property
    def total_tokens(self) -> int:
        """Sum of input and output tokens."""
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class GenerationResponse:
    """A provider-neutral response from a generation call."""

    id: str
    model: str
    output: Message
    usage: TokenUsage | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.model, "model")
        if self.output.role is not MessageRole.ASSISTANT:
            raise DomainValidationError("output message role must be assistant")
