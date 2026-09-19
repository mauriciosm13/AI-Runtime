"""Schemas for the /v1/prompts endpoints."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from ai_runtime.domain.generation import MessageRole
from ai_runtime.domain.prompt import PromptMessageTemplate, PromptTemplate


class PromptMessageSchema(BaseModel):
    """One templated message. ``content`` may contain ``{{variable}}`` placeholders."""

    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str

    def to_domain(self) -> PromptMessageTemplate:
        """Map this API payload to a domain PromptMessageTemplate."""
        return PromptMessageTemplate(role=self.role, content=self.content)


class CreatePromptRequest(BaseModel):
    """HTTP body for creating the next version of a named prompt."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    messages: list[PromptMessageSchema] = Field(min_length=1)


class PromptVersionSchema(BaseModel):
    """One stored prompt version."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: int
    messages: list[PromptMessageSchema]
    variables: list[str]
    created_at: datetime

    @classmethod
    def from_domain(cls, template: PromptTemplate) -> "PromptVersionSchema":
        """Build an API schema from a domain PromptTemplate."""
        return cls(
            name=template.name,
            version=template.version,
            messages=[PromptMessageSchema(role=item.role, content=item.content) for item in template.messages],
            variables=sorted(template.placeholders),
            created_at=template.created_at,
        )


class PromptVersionsSchema(BaseModel):
    """All versions of a named prompt."""

    model_config = ConfigDict(extra="forbid")

    versions: list[PromptVersionSchema]
