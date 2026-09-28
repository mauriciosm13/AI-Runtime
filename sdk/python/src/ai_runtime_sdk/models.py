"""Types for the public AI Runtime HTTP API.

Unknown JSON fields are ignored so additive API changes do not break callers.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class MessageRole(StrEnum):
    """Roles accepted on generation and prompt messages."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """A model-requested tool invocation."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    arguments: str


class ToolDefinition(BaseModel):
    """A tool the model may call. The runtime does not execute it."""

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    """One conversation message."""

    model_config = ConfigDict(extra="ignore")

    role: MessageRole
    content: str = ""
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class PromptReference(BaseModel):
    """A stored prompt template and the variable values for one call."""

    model_config = ConfigDict(extra="ignore")

    name: str
    version: int | None = None
    variables: dict[str, str] = Field(default_factory=dict)


class Context(BaseModel):
    """Optional input-token budget. Presence of this object enables the budget check."""

    model_config = ConfigDict(extra="ignore")

    max_input_tokens: int | None = None
    truncate: bool = False


class TokenUsage(BaseModel):
    """Token accounting returned with a completed response."""

    model_config = ConfigDict(extra="ignore")

    input_tokens: int
    output_tokens: int
    total_tokens: int


class Response(BaseModel):
    """A completed model response.

    ``request_id`` comes from the ``X-Request-ID`` response header, not the JSON body.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    model: str
    output: Message
    usage: TokenUsage | None = None
    cached: bool = False
    request_id: str | None = None


class ResponseDelta(BaseModel):
    """One incremental text chunk from a streaming response."""

    model_config = ConfigDict(extra="ignore")

    id: str
    model: str
    content: str
    request_id: str | None = None


class PromptMessage(BaseModel):
    """One templated message. ``content`` may contain ``{{variable}}`` placeholders."""

    model_config = ConfigDict(extra="ignore")

    role: MessageRole
    content: str


class PromptVersion(BaseModel):
    """One immutable version of a named prompt template."""

    model_config = ConfigDict(extra="ignore")

    name: str
    version: int
    messages: list[PromptMessage]
    variables: list[str]
    created_at: datetime
    request_id: str | None = None


class PromptList(BaseModel):
    """Every stored version of a named prompt, oldest first."""

    model_config = ConfigDict(extra="ignore")

    versions: list[PromptVersion]
    request_id: str | None = None
