"""Unit tests for the OpenAI EmbeddingProvider adapter with simulated HTTP."""

import asyncio
import json
from collections.abc import Callable
import httpx
import pytest
from ai_runtime.domain.embedding import EmbeddingRequest, EmbeddingResponse
from ai_runtime.ports.embedding_provider import EmbeddingProvider
from ai_runtime.providers.openai import OpenAIEmbeddingProvider, OpenAIProviderError

_API_KEY = "test-api-key"
_BASE_URL = "https://api.openai.test/v1"
_DIMENSIONS = 4


def _make_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _sample_request() -> EmbeddingRequest:
    return EmbeddingRequest(model="text-embedding-3-small", input=("hello world",))


def _success_payload() -> dict[str, object]:
    return {
        "id": "emb-123",
        "model": "text-embedding-3-small",
        "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3, 0.4]}],
        "usage": {"prompt_tokens": 2, "total_tokens": 2},
    }


def test_openai_embedding_provider_satisfies_protocol() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_payload())

    provider = OpenAIEmbeddingProvider(api_key=_API_KEY, http_client=_make_client(handler), base_url=_BASE_URL)
    assert isinstance(provider, EmbeddingProvider)


def test_embed_posts_openai_embeddings_body() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_success_payload())

    provider = OpenAIEmbeddingProvider(api_key=_API_KEY, http_client=_make_client(handler), base_url=_BASE_URL)
    asyncio.run(provider.embed(_sample_request()))
    assert captured["method"] == "POST"
    assert captured["url"] == f"{_BASE_URL}/embeddings"
    assert captured["body"] == {"model": "text-embedding-3-small", "input": ["hello world"]}


def test_embed_maps_success_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_payload())

    provider = OpenAIEmbeddingProvider(api_key=_API_KEY, http_client=_make_client(handler), base_url=_BASE_URL)
    result = asyncio.run(provider.embed(_sample_request()))
    assert isinstance(result, EmbeddingResponse)
    assert result.id == "emb-123"
    assert len(result.data) == 1
    assert len(result.data[0].values) == _DIMENSIONS
    assert result.usage.input_tokens == 2


def test_embed_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    provider = OpenAIEmbeddingProvider(api_key=_API_KEY, http_client=_make_client(handler), base_url=_BASE_URL)
    with pytest.raises(OpenAIProviderError):
        asyncio.run(provider.embed(_sample_request()))
