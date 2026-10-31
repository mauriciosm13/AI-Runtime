"""OpenAI Embeddings adapter implementing EmbeddingProvider."""

from typing import Any
import httpx
from ai_runtime.domain.embedding import EmbeddingRequest, EmbeddingResponse, EmbeddingUsage, EmbeddingVector
from ai_runtime.providers.openai.errors import OpenAIProviderError

_DEFAULT_OPENAI_API_URL = "https://api.openai.com/v1"


def _to_openai_body(request: EmbeddingRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": request.model,
        "input": list(request.input) if len(request.input) == 1 else list(request.input),
    }
    if request.dimensions is not None:
        body["dimensions"] = request.dimensions
    return body


def _from_openai_payload(payload: dict[str, Any], request: EmbeddingRequest) -> EmbeddingResponse:
    try:
        response_id = payload.get("id")
        if not isinstance(response_id, str) or not response_id.strip():
            response_id = "openai-embedding"
        model = payload.get("model")
        if not isinstance(model, str) or not model.strip():
            model = request.model
        data_payload = payload.get("data")
        if not isinstance(data_payload, list) or not data_payload:
            raise OpenAIProviderError("OpenAI embedding response is missing data")
        vectors: list[EmbeddingVector] = []
        for item in data_payload:
            if not isinstance(item, dict):
                raise OpenAIProviderError("OpenAI embedding response data is invalid")
            index = item.get("index")
            embedding = item.get("embedding")
            if not isinstance(index, int) or index < 0:
                raise OpenAIProviderError("OpenAI embedding response data is invalid")
            if not isinstance(embedding, list) or not embedding:
                raise OpenAIProviderError("OpenAI embedding response data is invalid")
            values = tuple(float(value) for value in embedding)
            vectors.append(EmbeddingVector(index=index, values=values))
        vectors.sort(key=lambda item: item.index)
        usage_payload = payload.get("usage")
        if not isinstance(usage_payload, dict):
            raise OpenAIProviderError("OpenAI embedding response usage is invalid")
        prompt_tokens = usage_payload.get("prompt_tokens")
        if not isinstance(prompt_tokens, int) or prompt_tokens < 0:
            raise OpenAIProviderError("OpenAI embedding response usage is invalid")
        return EmbeddingResponse(
            id=response_id,
            model=model,
            data=tuple(vectors),
            usage=EmbeddingUsage(input_tokens=prompt_tokens),
        )
    except OpenAIProviderError:
        raise
    except (TypeError, ValueError) as err:
        raise OpenAIProviderError("OpenAI embedding response payload is malformed") from err


class OpenAIEmbeddingProvider:
    """EmbeddingProvider adapter for OpenAI /v1/embeddings over HTTP."""

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient,
        base_url: str = _DEFAULT_OPENAI_API_URL,
    ) -> None:
        if not api_key.strip():
            raise OpenAIProviderError("api_key must not be empty or blank")
        if not base_url.strip():
            raise OpenAIProviderError("base_url must not be empty or blank")
        self._api_key = api_key
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Invoke OpenAI Embeddings and return an EmbeddingResponse."""
        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = _to_openai_body(request)
        try:
            response = await self._http_client.post(url, json=body, headers=headers)
        except httpx.HTTPError as err:
            raise OpenAIProviderError.transient("OpenAI HTTP request failed") from err
        if response.status_code >= 400:
            raise OpenAIProviderError.from_http_status(
                f"OpenAI HTTP request failed with status {response.status_code}",
                response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as err:
            raise OpenAIProviderError("OpenAI response body is not valid JSON") from err
        if not isinstance(payload, dict):
            raise OpenAIProviderError("OpenAI response body must be a JSON object")
        return _from_openai_payload(payload, request)
