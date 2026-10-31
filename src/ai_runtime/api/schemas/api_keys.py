"""Schemas for operator API key endpoints."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from ai_runtime.domain.api_key import ApiKeyMetadata, ApiKeyStatus


class CreateApiKeyRequest(BaseModel):
    """HTTP body for creating an API key."""

    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    name: str | None = Field(default=None, min_length=1)


class ApiKeySchema(BaseModel):
    """API key metadata without secret material."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    organization_id: UUID
    name: str | None
    prefix: str
    status: ApiKeyStatus
    created_at: datetime
    revoked_at: datetime | None
    updated_at: datetime

    @classmethod
    def from_domain(cls, metadata: ApiKeyMetadata) -> "ApiKeySchema":
        """Build an API schema from domain ApiKeyMetadata."""
        return cls(
            id=metadata.id,
            organization_id=metadata.organization_id,
            name=metadata.name,
            prefix=metadata.prefix,
            status=metadata.status,
            created_at=metadata.created_at,
            revoked_at=metadata.revoked_at,
            updated_at=metadata.updated_at,
        )


class CreateApiKeyResponse(ApiKeySchema):
    """Creation response including the one-time plaintext secret."""

    secret: str


class ApiKeyListSchema(BaseModel):
    """Listed API keys for an organization."""

    model_config = ConfigDict(extra="forbid")

    api_keys: list[ApiKeySchema]
