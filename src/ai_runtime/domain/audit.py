"""Durable audit-event contracts. Events never carry prompt or secret material."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID
from ai_runtime.domain.generation import DomainValidationError

_FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "authorization",
        "content",
        "messages",
        "password",
        "prompt",
        "secret",
        "token",
    }
)


def _require_non_blank(value: str, field_name: str) -> None:
    """Reject empty or whitespace-only strings."""
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty or blank")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """A security-relevant action recorded without request or response bodies."""

    id: UUID
    action: str
    occurred_at: datetime
    organization_id: UUID | None = None
    actor_api_key_id: UUID | None = None
    request_id: str | None = None
    resource_type: str = ""
    resource_id: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_blank(self.action, "action")
        _require_non_blank(self.resource_type, "resource_type")
        if self.occurred_at.tzinfo is None:
            raise DomainValidationError("occurred_at must be timezone-aware")
        raw = dict(self.metadata)
        object.__setattr__(self, "metadata", raw)
        for key, value in raw.items():
            _require_non_blank(key, "metadata key")
            if key.lower() in _FORBIDDEN_METADATA_KEYS:
                raise DomainValidationError(f"metadata key {key!r} is not allowed")
            if not isinstance(value, str):
                raise DomainValidationError("metadata values must be strings")
            if not value.strip():
                raise DomainValidationError("metadata values must not be blank")
