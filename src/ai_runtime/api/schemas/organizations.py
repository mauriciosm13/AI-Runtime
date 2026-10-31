"""Schemas for operator organization endpoints."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from ai_runtime.domain.organization import Organization, OrganizationStatus


class CreateOrganizationRequest(BaseModel):
    """HTTP body for creating an organization."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)


class OrganizationSchema(BaseModel):
    """Organization tenant returned by operator routes."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    slug: str
    status: OrganizationStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, organization: Organization) -> "OrganizationSchema":
        """Build an API schema from a domain Organization."""
        return cls(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            status=organization.status,
            created_at=organization.created_at,
            updated_at=organization.updated_at,
        )
