"""Unit tests for audit-event domain invariants."""

from datetime import UTC, datetime
from uuid import uuid4
import pytest
from ai_runtime.domain.audit import AuditEvent
from ai_runtime.domain.generation import DomainValidationError


def test_audit_event_rejects_prompt_metadata() -> None:
    """Audit metadata cannot store prompt or secret fields."""
    with pytest.raises(DomainValidationError, match="not allowed"):
        AuditEvent(
            id=uuid4(),
            action="response.created",
            occurred_at=datetime.now(UTC),
            resource_type="response",
            metadata={"prompt": "hello"},
        )


def test_audit_event_requires_timezone() -> None:
    """occurred_at must be timezone-aware."""
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        AuditEvent(
            id=uuid4(),
            action="response.created",
            occurred_at=datetime.now(),
            resource_type="response",
        )
