"""OpenAI Chat Completions adapter implementing ModelProvider."""

from typing import Any
import httpx
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, Message, MessageRole, TokenUsage
from ai_runtime.providers.openai.errors import OpenAIProviderError

_DEFAULT_OPENAI_API_URL = "https://api.openai.com/v1"


def _to_openai_body(request: GenerationRequest) -> dict[str, Any]:
    """Map a GenerationRequest to an OpenAI Chat Completions JSON body."""
    body: dict[str, Any] = {
        "model": request.model,
        "messages": [{"role": message.role.value, "content": message.content} for message in request.messages],
    }
    if request.temperature is not None:
        body["temperature"] = request.temperature
    if request.max_output_tokens is not None:
        body["max_tokens"] = request.max_output_tokens
    return body


def _from_openai_payload(
    payload: dict[str, Any],
    request: GenerationRequest,
) -> GenerationResponse:
    """Map an OpenAI Chat Completions JSON payload to GenerationResponse."""
    try:
        response_id = payload["id"]
        if not isinstance(response_id, str) or not response_id.strip():
            raise OpenAIProviderError("OpenAI response is missing a valid id")
        model = payload.get("model")
        if not isinstance(model, str) or not model.strip():
            model = request.model
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise OpenAIProviderError("OpenAI response is missing choices")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise OpenAIProviderError("OpenAI response choice is invalid")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise OpenAIProviderError("OpenAI response choice is missing message")
        content = message.get("content")
        if not isinstance(content, str):
            raise OpenAIProviderError("OpenAI response message is missing content")
        usage_payload = payload.get("usage")
        usage: TokenUsage | None = None
        if isinstance(usage_payload, dict):
            prompt_tokens = usage_payload.get("prompt_tokens")
            completion_tokens = usage_payload.get("completion_tokens")
            if not isinstance(prompt_tokens, int) or not isinstance(completion_tokens, int):
                raise OpenAIProviderError("OpenAI response usage is invalid")
            usage = TokenUsage(input_tokens=prompt_tokens, output_tokens=completion_tokens)
        return GenerationResponse(
            id=response_id,
            model=model,
            output=Message(role=MessageRole.ASSISTANT, content=content),
            usage=usage,
        )
    except OpenAIProviderError:
        raise
    except (KeyError, TypeError, ValueError) as err:
        raise OpenAIProviderError("OpenAI response payload is malformed") from err


class OpenAIModelProvider:
    """ModelProvider adapter for OpenAI Chat Completions over HTTP."""

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

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Invoke OpenAI Chat Completions and return a GenerationResponse."""
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = _to_openai_body(request)
        try:
            response = await self._http_client.post(url, json=body, headers=headers)
        except httpx.HTTPError as err:
            raise OpenAIProviderError("OpenAI HTTP request failed") from err
        if response.status_code >= 400:
            raise OpenAIProviderError(f"OpenAI HTTP request failed with status {response.status_code}")
        try:
            payload = response.json()
        except ValueError as err:
            raise OpenAIProviderError("OpenAI response body is not valid JSON") from err
        if not isinstance(payload, dict):
            raise OpenAIProviderError("OpenAI response body must be a JSON object")
        return _from_openai_payload(payload, request)
