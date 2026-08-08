"""Organization access policy domain contracts and invariants."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID
from ai_runtime.domain.generation import DomainValidationError


class ModelNotAvailableError(Exception):
    """Raised when the requested model is not entitled for the organization."""

    def __init__(self, *, model: str) -> None:
        self.model = model
        super().__init__("The requested model is not available for this organization.")


class QuotaExceededError(Exception):
    """Raised when an organization exceeds its monthly token quota."""

    def __init__(self, *, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Monthly token quota exceeded.")


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty or blank")


@dataclass(frozen=True, slots=True)
class OrganizationPolicy:
    """Per-organization usage limits. Null limits mean unlimited."""

    organization_id: UUID
    monthly_token_limit: int | None = None

    def __post_init__(self) -> None:
        if self.monthly_token_limit is not None and self.monthly_token_limit <= 0:
            raise DomainValidationError("monthly_token_limit must be greater than zero when set")


@dataclass(frozen=True, slots=True)
class ModelEntitlement:
    """A model an organization is allowed to invoke."""

    organization_id: UUID
    model: str

    def __post_init__(self) -> None:
        _require_non_blank(self.model, "model")


def is_model_allowed(requested_model: str, entitlements: frozenset[str]) -> bool:
    """Return whether ``requested_model`` is allowed for the organization.

    An empty entitlement set means all models are allowed.
    """
    if not entitlements:
        return True
    return requested_model in entitlements


def would_exceed_monthly_quota(current_tokens: int, limit: int, estimated_additional: int = 0) -> bool:
    """Return whether usage would exceed a monthly token limit."""
    if limit <= 0:
        raise DomainValidationError("limit must be greater than zero")
    if current_tokens < 0 or estimated_additional < 0:
        raise DomainValidationError("token counts must not be negative")
    return current_tokens + estimated_additional >= limit


def current_month_utc_bounds(*, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return inclusive start and exclusive end for the current UTC calendar month."""
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise DomainValidationError("now must be timezone-aware")
    start = instant.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def seconds_until_end_of_month_utc(*, now: datetime | None = None) -> int:
    """Return whole seconds until the next UTC month boundary."""
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise DomainValidationError("now must be timezone-aware")
    _, end = current_month_utc_bounds(now=instant)
    delta = end - instant
    return max(1, int(delta.total_seconds()))
