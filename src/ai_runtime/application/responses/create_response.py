"""Use case for creating a provider-neutral model response."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse
from ai_runtime.domain.usage import UsageRecord
from ai_runtime.ports.cost_estimator import CostEstimator
from ai_runtime.ports.model_provider import ModelProvider
from ai_runtime.ports.usage_repository import UsageRepository


@dataclass(frozen=True, slots=True)
class CreateResponseCommand:
    """Authenticated generation request with correlation and tenancy context."""

    request: GenerationRequest
    request_id: str
    organization_id: UUID
    api_key_id: UUID


class CreateResponse:
    """Coordinate generation, then persist usage/tokens/estimated cost."""

    def __init__(
        self,
        model_provider: ModelProvider,
        usage_records: UsageRepository,
        cost_estimator: CostEstimator,
        *,
        provider_name: str = "openai",
    ) -> None:
        self._model_provider = model_provider
        self._usage_records = usage_records
        self._cost_estimator = cost_estimator
        self._provider_name = provider_name

    async def execute(self, command: CreateResponseCommand) -> GenerationResponse:
        """Generate a response, record usage accounting, then return the result.

        Provider invocation is outside the usage persistence transaction. Usage
        is written only after a successful provider response.
        """
        response = await self._model_provider.generate(command.request)
        estimated_cost = self._cost_estimator.estimate(
            provider=self._provider_name,
            model=response.model,
            usage=response.usage,
        )
        input_tokens = response.usage.input_tokens if response.usage is not None else None
        output_tokens = response.usage.output_tokens if response.usage is not None else None
        await self._usage_records.add(
            UsageRecord(
                id=uuid4(),
                request_id=command.request_id,
                organization_id=command.organization_id,
                api_key_id=command.api_key_id,
                provider=self._provider_name,
                model=response.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimated_cost,
                created_at=datetime.now(UTC),
            )
        )
        return response
