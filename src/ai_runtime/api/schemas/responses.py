"""Schemas for POST /v1/responses."""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator
from ai_runtime.domain.generation import DomainValidationError, GenerationRequest, GenerationResponse
from ai_runtime.domain.generation import Message, MessageRole, TokenUsage, ToolCall, ToolDefinition


class ToolCallSchema(BaseModel):
    """A model-requested tool invocation."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: str = Field(min_length=1)

    def to_domain(self) -> ToolCall:
        """Map this API payload to a domain ToolCall."""
        return ToolCall(id=self.id, name=self.name, arguments=self.arguments)

    @classmethod
    def from_domain(cls, tool_call: ToolCall) -> "ToolCallSchema":
        """Build an API schema from a domain ToolCall."""
        return cls(id=tool_call.id, name=tool_call.name, arguments=tool_call.arguments)


class ToolDefinitionSchema(BaseModel):
    """A client-declared tool the model may call."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)

    def to_domain(self) -> ToolDefinition:
        """Map this API payload to a domain ToolDefinition."""
        return ToolDefinition(name=self.name, description=self.description, parameters=self.parameters)


class MessageSchema(BaseModel):
    """A single conversation message in an API request or response."""

    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str = ""
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[ToolCallSchema] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_role_fields(self) -> "MessageSchema":
        """Reject combinations that the domain would also reject."""
        try:
            Message(
                role=self.role,
                content=self.content,
                tool_call_id=self.tool_call_id,
                name=self.name,
                tool_calls=tuple(item.to_domain() for item in self.tool_calls),
            )
        except DomainValidationError as err:
            raise ValueError(str(err)) from err
        return self

    @model_serializer(mode="wrap")
    def _omit_empty_tool_fields(self, serializer: Any) -> dict[str, Any]:
        """Keep the existing JSON shape when no tool fields are set."""
        payload = dict(serializer(self))
        if not payload.get("tool_calls"):
            payload.pop("tool_calls", None)
        if payload.get("tool_call_id") is None:
            payload.pop("tool_call_id", None)
        if payload.get("name") is None:
            payload.pop("name", None)
        return payload

    def to_domain(self) -> Message:
        """Map this API payload to a domain Message."""
        return Message(
            role=self.role,
            content=self.content,
            tool_call_id=self.tool_call_id,
            name=self.name,
            tool_calls=tuple(item.to_domain() for item in self.tool_calls),
        )

    @classmethod
    def from_domain(cls, message: Message) -> "MessageSchema":
        """Build an API schema from a domain Message."""
        return cls(
            role=message.role,
            content=message.content,
            tool_call_id=message.tool_call_id,
            name=message.name,
            tool_calls=[ToolCallSchema.from_domain(item) for item in message.tool_calls],
        )


class CreateResponseRequest(BaseModel):
    """HTTP body for creating a provider-neutral model response."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    messages: list[MessageSchema] = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    stream: bool = False
    tools: list[ToolDefinitionSchema] = Field(default_factory=list)

    def to_domain(self) -> GenerationRequest:
        """Map this API payload to a domain GenerationRequest."""
        return GenerationRequest(
            model=self.model,
            messages=tuple(message.to_domain() for message in self.messages),
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            stream=self.stream,
            tools=tuple(tool.to_domain() for tool in self.tools),
        )


class TokenUsageSchema(BaseModel):
    """Token accounting exposed in an API response."""

    model_config = ConfigDict(extra="forbid")

    input_tokens: int
    output_tokens: int
    total_tokens: int

    @classmethod
    def from_domain(cls, usage: TokenUsage) -> "TokenUsageSchema":
        """Build an API schema from a domain TokenUsage."""
        return cls(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )


class ResponseSchema(BaseModel):
    """HTTP body returned after a successful model response."""

    model_config = ConfigDict(extra="forbid")

    id: str
    model: str
    output: MessageSchema
    usage: TokenUsageSchema | None = None

    @classmethod
    def from_domain(cls, response: GenerationResponse) -> "ResponseSchema":
        """Build an API schema from a domain GenerationResponse."""
        usage = TokenUsageSchema.from_domain(response.usage) if response.usage is not None else None
        return cls(
            id=response.id,
            model=response.model,
            output=MessageSchema.from_domain(response.output),
            usage=usage,
        )
