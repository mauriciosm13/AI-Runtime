"""API key credential domain contracts and invariants.

Plaintext secrets are never part of the persisted entity. ``secret_hash`` is a
one-way KDF digest (argon2id at the infrastructure boundary); ``prefix`` is a
non-secret display/lookup fragment insufficient for authentication.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID
from ai_runtime.domain.generation import DomainValidationError


class ApiKeyStatus(StrEnum):
    """Lifecycle status for an API key credential."""

    ACTIVE = "active"
    REVOKED = "revoked"


class ApiKeyNotFoundError(Exception):
    """Raised when an API key cannot be resolved by id."""


class ApiKeyAlreadyRevokedError(Exception):
    """Raised when revoke is attempted on a key that is already revoked.

    RevokeApiKey uses this for an explicit non-idempotent revoke policy.
    """


def _require_non_blank(value: str, field_name: str) -> None:
    """Reject empty or whitespace-only strings."""
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty or blank")


@dataclass(frozen=True, slots=True)
class ApiKeyMetadata:
    """Public API-key projection without secret material or hash digests."""

    id: UUID
    organization_id: UUID
    name: str | None
    prefix: str
    status: ApiKeyStatus
    created_at: datetime
    revoked_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ApiKey:
    """A credential belonging to exactly one organization.

    ``secret_hash`` is stored for verification only and must never be logged or
    returned from list/get metadata use cases.
    """

    id: UUID
    organization_id: UUID
    name: str | None
    prefix: str
    secret_hash: str
    status: ApiKeyStatus
    created_at: datetime
    revoked_at: datetime | None
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.name is not None:
            _require_non_blank(self.name, "name")
        _require_non_blank(self.prefix, "prefix")
        _require_non_blank(self.secret_hash, "secret_hash")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise DomainValidationError("created_at and updated_at must be timezone-aware")
        if self.revoked_at is not None and self.revoked_at.tzinfo is None:
            raise DomainValidationError("revoked_at must be timezone-aware when set")
        if self.status is ApiKeyStatus.REVOKED and self.revoked_at is None:
            raise DomainValidationError("revoked keys must have revoked_at set")
        if self.status is ApiKeyStatus.ACTIVE and self.revoked_at is not None:
            raise DomainValidationError("active keys must not have revoked_at set")

    def to_metadata(self) -> ApiKeyMetadata:
        """Return the non-secret projection of this key."""
        return ApiKeyMetadata(
            id=self.id,
            organization_id=self.organization_id,
            name=self.name,
            prefix=self.prefix,
            status=self.status,
            created_at=self.created_at,
            revoked_at=self.revoked_at,
            updated_at=self.updated_at,
        )

    def revoke(self, at: datetime) -> "ApiKey":
        """Return a revoked copy of this key.

        Raises ``ApiKeyAlreadyRevokedError`` when the key is already revoked
        (explicit non-idempotent policy).
        """
        if self.status is ApiKeyStatus.REVOKED:
            raise ApiKeyAlreadyRevokedError(f"api key already revoked: {self.id}")
        if at.tzinfo is None:
            raise DomainValidationError("revoke timestamp must be timezone-aware")
        return replace(self, status=ApiKeyStatus.REVOKED, revoked_at=at, updated_at=at)
