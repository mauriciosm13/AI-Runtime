"""Schemas for the provider-neutral API error envelope."""

from pydantic import BaseModel, ConfigDict, Field
from ai_runtime.api.errors import ErrorCode


class ErrorDetailSchema(BaseModel):
    """Machine-readable error payload returned to clients."""

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str = Field(min_length=1)
    request_id: str | None = None


class ErrorResponseSchema(BaseModel):
    """Top-level error response wrapper."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetailSchema
