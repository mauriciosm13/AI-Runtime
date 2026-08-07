"""Unit tests for the RateLimiter port contract."""

import asyncio
from uuid import UUID, uuid4
from ai_runtime.ports.rate_limiter import RateLimitDecision, RateLimiter


class FakeRateLimiter:
    """In-memory stand-in that satisfies RateLimiter."""

    async def consume(self, organization_id: UUID) -> RateLimitDecision:
        _ = organization_id
        return RateLimitDecision(allowed=True)


def test_fake_rate_limiter_satisfies_contract() -> None:
    """A structural fake is accepted as RateLimiter."""
    limiter: RateLimiter = FakeRateLimiter()
    assert isinstance(limiter, RateLimiter)
    decision = asyncio.run(limiter.consume(uuid4()))
    assert decision.allowed is True
    assert decision.retry_after_seconds is None
