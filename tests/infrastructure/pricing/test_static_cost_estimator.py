"""Unit tests for StaticCostEstimator."""

from decimal import Decimal
from ai_runtime.domain.generation import TokenUsage
from ai_runtime.infrastructure.pricing import StaticCostEstimator


def test_estimates_known_openai_model() -> None:
    """Known OpenAI model prices produce a quantized USD estimate."""
    estimator = StaticCostEstimator()
    cost = estimator.estimate(
        provider="openai",
        model="gpt-4o-mini",
        usage=TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000),
    )
    assert cost == Decimal("0.75000000")


def test_returns_none_for_unknown_model_or_missing_usage() -> None:
    """Unknown models and missing usage yield None rather than inventing cost."""
    estimator = StaticCostEstimator()
    assert estimator.estimate(provider="openai", model="unknown-model", usage=TokenUsage(1, 1)) is None
    assert estimator.estimate(provider="openai", model="gpt-4o-mini", usage=None) is None
    assert estimator.estimate(provider="anthropic", model="gpt-4o-mini", usage=TokenUsage(1, 1)) is None
