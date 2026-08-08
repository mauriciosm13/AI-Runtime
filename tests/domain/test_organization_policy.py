"""Unit tests for organization policy domain rules."""

from datetime import UTC, datetime

import pytest

from ai_runtime.domain.generation import DomainValidationError
from ai_runtime.domain.organization_policy import (
    OrganizationPolicy,
    current_month_utc_bounds,
    is_model_allowed,
    seconds_until_end_of_month_utc,
    would_exceed_monthly_quota,
)
from uuid import uuid4


def test_is_model_allowed_when_entitlements_empty() -> None:
    assert is_model_allowed("gpt-4o-mini", frozenset()) is True


def test_is_model_allowed_when_model_in_allowlist() -> None:
    assert is_model_allowed("gpt-4o-mini", frozenset({"gpt-4o-mini"})) is True


def test_is_model_allowed_when_model_not_in_allowlist() -> None:
    assert is_model_allowed("gpt-4o", frozenset({"gpt-4o-mini"})) is False


def test_would_exceed_monthly_quota_at_limit() -> None:
    assert would_exceed_monthly_quota(1000, 1000) is True


def test_would_exceed_monthly_quota_below_limit() -> None:
    assert would_exceed_monthly_quota(900, 1000) is False


def test_would_exceed_monthly_quota_with_estimated_additional() -> None:
    assert would_exceed_monthly_quota(900, 1000, 50) is False
    assert would_exceed_monthly_quota(900, 1000, 100) is True


def test_organization_policy_rejects_non_positive_limit() -> None:
    with pytest.raises(DomainValidationError, match="monthly_token_limit"):
        OrganizationPolicy(organization_id=uuid4(), monthly_token_limit=0)


def test_current_month_utc_bounds() -> None:
    start, end = current_month_utc_bounds(now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC))
    assert start == datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 1, 0, 0, tzinfo=UTC)


def test_seconds_until_end_of_month_utc() -> None:
    now = datetime(2026, 8, 31, 23, 0, tzinfo=UTC)
    assert seconds_until_end_of_month_utc(now=now) == 3600
