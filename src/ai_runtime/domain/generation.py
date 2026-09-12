"""Provider-neutral generation contracts for text model invocations."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DomainValidationError(ValueError):
    """Raised when generation domain data violates an invariant."""


class MessageRole(StrEnum):
    """Roles recognized in a generation conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


def _require_non_blank(value: str, field_name: str) -> None:
    """Reject empty or whitespace-only strings."""
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty or blank")


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """A client-declared tool the model may call."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_blank(self.name, "name")
        if not isinstance(self.parameters, dict):
            raise DomainValidationError("parameters must be a JSON object")


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A model request to invoke a declared tool."""

    id: str
    name: str
    arguments: str

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.name, "name")
        if not self.arguments.strip():
            raise DomainValidationError("arguments must not be empty or blank")


@dataclass(frozen=True, slots=True)
class Message:
    """A single conversation message with a role and textual content."""

    role: MessageRole
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()

    def __post_init__(self) -> None:
        if self.role is MessageRole.TOOL:
            if self.tool_call_id is None or not self.tool_call_id.strip():
                raise DomainValidationError("tool_call_id is required for tool messages")
            _require_non_blank(self.content, "content")
            if self.tool_calls:
                raise DomainValidationError("tool messages cannot include tool_calls")
            return
        if self.tool_call_id is not None:
            raise DomainValidationError("tool_call_id is only valid for tool messages")
        if self.tool_calls:
            if self.role is not MessageRole.ASSISTANT:
                raise DomainValidationError("tool_calls are only valid on assistant messages")
            return
        _require_non_blank(self.content, "content")


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """A provider-neutral request to generate model output."""

    model: str
    messages: tuple[Message, ...]
    temperature: float | None = None
    max_output_tokens: int | None = None
    stream: bool = False
    tools: tuple[ToolDefinition, ...] = ()

    def __post_init__(self) -> None:
        _require_non_blank(self.model, "model")
        if not self.messages:
            raise DomainValidationError("messages must contain at least one message")
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise DomainValidationError("temperature must be between 0 and 2 inclusive")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise DomainValidationError("max_output_tokens must be greater than zero")
        if self.stream and self.uses_tools:
            raise DomainValidationError("tools are not supported for streaming requests.")

    @property
    def uses_tools(self) -> bool:
        """Return whether the request declares tools or includes tool messages."""
        if self.tools:
            return True
        return any(message.role is MessageRole.TOOL or message.tool_calls for message in self.messages)


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


@dataclass(frozen=True, slots=True)
class GenerationDelta:
    """An incremental assistant-text update from a streaming generation."""

    id: str
    model: str
    content: str

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.model, "model")
        if self.content == "":
            raise DomainValidationError("content must not be empty")


GenerationStreamEvent = GenerationDelta | GenerationResponse
