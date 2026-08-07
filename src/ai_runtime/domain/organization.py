"""Organization tenancy domain contracts and invariants."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID
from ai_runtime.domain.generation import DomainValidationError

_SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")


class OrganizationStatus(StrEnum):
    """Lifecycle status for an organization tenant."""

    ACTIVE = "active"
    SUSPENDED = "suspended"


class OrganizationSlugConflictError(Exception):
    """Raised when an organization slug is already in use."""


class OrganizationNotFoundError(Exception):
    """Raised when an organization cannot be resolved by id."""


class OrganizationSuspendedError(Exception):
    """Raised when an organization exists but is suspended from API use."""


def _require_non_blank(value: str, field_name: str) -> None:
    """Reject empty or whitespace-only strings."""
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty or blank")


def _require_valid_slug(slug: str) -> None:
    """Reject blank or malformed organization slugs."""
    _require_non_blank(slug, "slug")
    if not _SLUG_PATTERN.fullmatch(slug):
        raise DomainValidationError("slug must contain only lowercase letters, digits, and hyphens")


@dataclass(frozen=True, slots=True)
class Organization:
    """A tenant that owns credentials, policy, and usage."""

    id: UUID
    name: str
    slug: str
    status: OrganizationStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank(self.name, "name")
        _require_valid_slug(self.slug)
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise DomainValidationError("created_at and updated_at must be timezone-aware")
