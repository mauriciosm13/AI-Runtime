"""Port for estimating USD cost from provider/model token usage."""

from decimal import Decimal
from typing import Protocol, runtime_checkable
from ai_runtime.domain.generation import TokenUsage


@runtime_checkable
class CostEstimator(Protocol):
    """Estimate request cost from model pricing tables.

    Returns ``None`` when pricing is unknown or token usage is unavailable.
    """

    def estimate(
        self,
        *,
        provider: str,
        model: str,
        usage: TokenUsage | None,
    ) -> Decimal | None:
        """Return estimated USD cost, or ``None`` when cost cannot be computed."""
        ...
