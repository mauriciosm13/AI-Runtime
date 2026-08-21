"""Static per-model USD pricing table for estimated usage cost."""

from decimal import Decimal
from ai_runtime.domain.generation import TokenUsage
from ai_runtime.domain.usage import ModelPricing, estimate_cost_usd

# Approximate public list prices (USD per 1M tokens). Estimates only — not invoices.
_OPENAI_PRICING: dict[str, ModelPricing] = {
    "gpt-4o-mini": ModelPricing(
        input_usd_per_1m_tokens=Decimal("0.15"),
        output_usd_per_1m_tokens=Decimal("0.60"),
    ),
    "gpt-4o": ModelPricing(
        input_usd_per_1m_tokens=Decimal("2.50"),
        output_usd_per_1m_tokens=Decimal("10.00"),
    ),
}

_ANTHROPIC_PRICING: dict[str, ModelPricing] = {
    "claude-3-5-sonnet-20241022": ModelPricing(
        input_usd_per_1m_tokens=Decimal("3.00"),
        output_usd_per_1m_tokens=Decimal("15.00"),
    ),
}

_PROVIDER_PRICING: dict[str, dict[str, ModelPricing]] = {
    "openai": _OPENAI_PRICING,
    "anthropic": _ANTHROPIC_PRICING,
}


class StaticCostEstimator:
    """Look up static model prices and estimate USD cost from token usage."""

    def estimate(
        self,
        *,
        provider: str,
        model: str,
        usage: TokenUsage | None,
    ) -> Decimal | None:
        """Return estimated USD cost, or ``None`` when pricing/usage is missing."""
        if usage is None:
            return None
        provider_prices = _PROVIDER_PRICING.get(provider.strip().lower())
        if provider_prices is None:
            return None
        pricing = provider_prices.get(model.strip())
        if pricing is None:
            return None
        return estimate_cost_usd(usage, pricing)
