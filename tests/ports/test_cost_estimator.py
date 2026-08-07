"""Unit tests for the CostEstimator port contract."""

from decimal import Decimal
from ai_runtime.domain.generation import TokenUsage
from ai_runtime.ports.cost_estimator import CostEstimator


class FakeCostEstimator:
    """Deterministic stand-in that satisfies CostEstimator."""

    def estimate(
        self,
        *,
        provider: str,
        model: str,
        usage: TokenUsage | None,
    ) -> Decimal | None:
        if usage is None:
            return None
        return Decimal("0.01")


def test_fake_estimator_satisfies_cost_estimator_contract() -> None:
    """A structural fake is accepted as CostEstimator."""
    estimator: CostEstimator = FakeCostEstimator()
    assert isinstance(estimator, CostEstimator)
    assert estimator.estimate(provider="openai", model="gpt-4o-mini", usage=None) is None
    assert estimator.estimate(
        provider="openai",
        model="gpt-4o-mini",
        usage=TokenUsage(input_tokens=1, output_tokens=1),
    ) == Decimal("0.01")
