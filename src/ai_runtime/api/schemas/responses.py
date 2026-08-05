"""Schemas for POST /v1/responses."""

from pydantic import BaseModel, ConfigDict, Field
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, Message, MessageRole, TokenUsage


class MessageSchema(BaseModel):
    """A single conversation message in an API request or response."""

    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str = Field(min_length=1)


class CreateResponseRequest(BaseModel):
    """HTTP body for creating a provider-neutral model response."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    messages: list[MessageSchema] = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, gt=0)

    def to_domain(self) -> GenerationRequest:
        """Map this API payload to a domain GenerationRequest."""
        return GenerationRequest(
            model=self.model,
            messages=tuple(Message(role=message.role, content=message.content) for message in self.messages),
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
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
            output=MessageSchema(role=response.output.role, content=response.output.content),
            usage=usage,
        )
