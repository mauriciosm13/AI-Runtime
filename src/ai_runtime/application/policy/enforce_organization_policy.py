"""Use case for enforcing organization model access and monthly quotas."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID
from ai_runtime.domain.organization_policy import (
    ModelNotAvailableError,
    QuotaExceededError,
    current_month_utc_bounds,
    is_model_allowed,
    seconds_until_end_of_month_utc,
    would_exceed_monthly_quota,
)
from ai_runtime.ports.organization_policy_repository import OrganizationPolicyRepository
from ai_runtime.ports.usage_repository import UsageRepository


@dataclass(frozen=True, slots=True)
class EnforceOrganizationPolicyCommand:
    """Input for validating model access and monthly token quota."""

    organization_id: UUID
    requested_model: str
    max_output_tokens: int | None = None


class EnforceOrganizationPolicy:
    """Reject requests that violate organization entitlements or monthly quota."""

    def __init__(
        self,
        organization_policies: OrganizationPolicyRepository,
        usage_records: UsageRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._organization_policies = organization_policies
        self._usage_records = usage_records
        self._clock = clock or (lambda: datetime.now(UTC))

    async def execute(self, command: EnforceOrganizationPolicyCommand) -> None:
        """Validate model entitlement and monthly token quota before provider invocation."""
        entitlements = await self._organization_policies.list_entitlements(command.organization_id)
        allowed_models = frozenset(entry.model for entry in entitlements)
        if not is_model_allowed(command.requested_model, allowed_models):
            raise ModelNotAvailableError(model=command.requested_model)

        policy = await self._organization_policies.get_policy(command.organization_id)
        if policy.monthly_token_limit is None:
            return

        now = self._clock()
        period_start, period_end = current_month_utc_bounds(now=now)
        used_tokens = await self._usage_records.sum_tokens_for_organization_in_period(
            command.organization_id,
            start=period_start,
            end=period_end,
        )
        estimated_additional = command.max_output_tokens or 0
        if would_exceed_monthly_quota(used_tokens, policy.monthly_token_limit, estimated_additional):
            raise QuotaExceededError(retry_after_seconds=seconds_until_end_of_month_utc(now=now))
