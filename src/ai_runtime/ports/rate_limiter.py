"""Port for consuming organization request rate-limit budget."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Outcome of attempting to consume one request from the rate-limit budget."""

    allowed: bool
    retry_after_seconds: int | None = None


@runtime_checkable
class RateLimiter(Protocol):
    """Async contract for organization-scoped request rate limiting."""

    async def consume(self, organization_id: UUID) -> RateLimitDecision:
        """Consume one request token for ``organization_id``.

        Returns whether the request is allowed and, when denied, a suggested
        ``Retry-After`` delay in whole seconds.
        """
        ...
