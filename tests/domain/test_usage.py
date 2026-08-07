"""Unit tests for usage accounting domain contracts."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4
import pytest
from ai_runtime.domain.generation import DomainValidationError, TokenUsage
from ai_runtime.domain.usage import ModelPricing, UsageRecord, estimate_cost_usd


def _record(**overrides: object) -> UsageRecord:
    values: dict[str, object] = {
        "id": uuid4(),
        "request_id": "req_abc",
        "organization_id": uuid4(),
        "api_key_id": uuid4(),
        "provider": "openai",
        "model": "gpt-4o-mini",
        "input_tokens": 10,
        "output_tokens": 5,
        "estimated_cost_usd": Decimal("0.00000450"),
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    return UsageRecord(**values)  # type: ignore[arg-type]


def test_valid_usage_record_constructs() -> None:
    """A complete UsageRecord accepts token counts and estimated cost."""
    record = _record()
    assert record.provider == "openai"
    assert record.input_tokens == 10
    assert record.output_tokens == 5
    assert record.estimated_cost_usd == Decimal("0.00000450")


def test_usage_record_allows_null_tokens_and_cost() -> None:
    """Missing provider usage is represented with null token and cost fields."""
    record = _record(input_tokens=None, output_tokens=None, estimated_cost_usd=None)
    assert record.input_tokens is None
    assert record.output_tokens is None
    assert record.estimated_cost_usd is None


def test_estimate_cost_usd_uses_per_million_pricing() -> None:
    """Cost estimate multiplies token counts by USD-per-1M rates."""
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)
    pricing = ModelPricing(
        input_usd_per_1m_tokens=Decimal("0.15"),
        output_usd_per_1m_tokens=Decimal("0.60"),
    )
    assert estimate_cost_usd(usage, pricing) == Decimal("0.45000000")


def test_rejects_blank_request_id() -> None:
    """Blank request_id values are rejected."""
    with pytest.raises(DomainValidationError, match="request_id"):
        _record(request_id="   ")


def test_rejects_partial_token_counts() -> None:
    """input_tokens and output_tokens must both be set or both be None."""
    with pytest.raises(DomainValidationError, match="input_tokens and output_tokens"):
        _record(input_tokens=10, output_tokens=None)


def test_rejects_negative_estimated_cost() -> None:
    """Negative estimated costs are rejected."""
    with pytest.raises(DomainValidationError, match="estimated_cost_usd"):
        _record(estimated_cost_usd=Decimal("-0.01"))


def test_rejects_naive_created_at() -> None:
    """created_at must be timezone-aware."""
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        _record(created_at=datetime(2026, 1, 1))
