"""Usage accounting domain contracts and invariants.

Records request-level token consumption and estimated cost. Prompt and response
content are intentionally absent — content capture requires a future policy.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from ai_runtime.domain.generation import DomainValidationError, TokenUsage


def _require_non_blank(value: str, field_name: str) -> None:
    """Reject empty or whitespace-only strings."""
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty or blank")


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """USD price per one million tokens for input and output."""

    input_usd_per_1m_tokens: Decimal
    output_usd_per_1m_tokens: Decimal

    def __post_init__(self) -> None:
        if self.input_usd_per_1m_tokens < 0:
            raise DomainValidationError("input_usd_per_1m_tokens must not be negative")
        if self.output_usd_per_1m_tokens < 0:
            raise DomainValidationError("output_usd_per_1m_tokens must not be negative")


def estimate_cost_usd(usage: TokenUsage, pricing: ModelPricing) -> Decimal:
    """Estimate USD cost from token counts and per-million pricing."""
    million = Decimal("1000000")
    input_cost = (Decimal(usage.input_tokens) / million) * pricing.input_usd_per_1m_tokens
    output_cost = (Decimal(usage.output_tokens) / million) * pricing.output_usd_per_1m_tokens
    return (input_cost + output_cost).quantize(Decimal("0.00000001"))


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """Durable accounting row for one authenticated generation request.

    ``request_id`` is the correlation identifier used for retries and
    reconciliation so the same HTTP request is not double-counted.
    """

    id: UUID
    request_id: str
    organization_id: UUID
    api_key_id: UUID
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: Decimal | None
    created_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank(self.request_id, "request_id")
        _require_non_blank(self.provider, "provider")
        _require_non_blank(self.model, "model")
        if self.created_at.tzinfo is None:
            raise DomainValidationError("created_at must be timezone-aware")
        if self.input_tokens is not None and self.input_tokens < 0:
            raise DomainValidationError("input_tokens must not be negative")
        if self.output_tokens is not None and self.output_tokens < 0:
            raise DomainValidationError("output_tokens must not be negative")
        if self.estimated_cost_usd is not None and self.estimated_cost_usd < 0:
            raise DomainValidationError("estimated_cost_usd must not be negative")
        if (self.input_tokens is None) != (self.output_tokens is None):
            raise DomainValidationError("input_tokens and output_tokens must both be set or both be None")
