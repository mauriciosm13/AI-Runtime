"""Unit tests for the EmbeddingProvider port contract."""

import asyncio
from ai_runtime.domain.embedding import EmbeddingRequest, EmbeddingResponse, EmbeddingUsage, EmbeddingVector
from ai_runtime.ports.embedding_provider import EmbeddingProvider


class FakeEmbeddingProvider:
    """Deterministic stand-in that satisfies EmbeddingProvider."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(
            id="fake_emb_1",
            model=request.model,
            data=tuple(
                EmbeddingVector(index=position, values=(float(position), 1.0))
                for position, _text in enumerate(request.input)
            ),
            usage=EmbeddingUsage(input_tokens=len(request.input)),
        )


def test_fake_provider_satisfies_embedding_provider_contract() -> None:
    """A structural fake is accepted as EmbeddingProvider and can embed."""
    provider: EmbeddingProvider = FakeEmbeddingProvider()
    assert isinstance(provider, EmbeddingProvider)
    request = EmbeddingRequest(model="fake-embed", input=("alpha", "beta"))
    response = asyncio.run(provider.embed(request))
    assert response.model == "fake-embed"
    assert len(response.data) == 2
    assert response.data[0].index == 0
    assert response.data[1].values == (1.0, 1.0)
