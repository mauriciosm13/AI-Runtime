"""Anthropic Messages API adapter implementing ModelProvider."""

from typing import Any
import httpx
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, Message, MessageRole, TokenUsage
from ai_runtime.providers.anthropic.errors import AnthropicProviderError

_DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
_ANTHROPIC_API_VERSION = "2023-06-01"
_DEFAULT_MAX_OUTPUT_TOKENS = 1024


def _split_system_messages(request: GenerationRequest) -> tuple[str | None, list[Message]]:
    """Extract system messages for Anthropic's ``system`` field; return the rest."""
    system_parts: list[str] = []
    conversation: list[Message] = []
    for message in request.messages:
        if message.role is MessageRole.SYSTEM:
            system_parts.append(message.content)
        else:
            conversation.append(message)
    system = "\n\n".join(system_parts) if system_parts else None
    return system, conversation


def _to_anthropic_body(request: GenerationRequest) -> dict[str, Any]:
    """Map a GenerationRequest to an Anthropic Messages JSON body."""
    system, conversation = _split_system_messages(request)
    if not conversation:
        raise AnthropicProviderError("messages must contain at least one non-system message")
    max_tokens = request.max_output_tokens if request.max_output_tokens is not None else _DEFAULT_MAX_OUTPUT_TOKENS
    body: dict[str, Any] = {
        "model": request.model,
        "max_tokens": max_tokens,
        "messages": [{"role": message.role.value, "content": message.content} for message in conversation],
    }
    if system is not None:
        body["system"] = system
    if request.temperature is not None:
        body["temperature"] = request.temperature
    return body


def _text_from_content_blocks(content_blocks: object) -> str:
    """Join Anthropic text blocks into a single assistant string."""
    if not isinstance(content_blocks, list) or not content_blocks:
        raise AnthropicProviderError("Anthropic response is missing content")
    parts: list[str] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            raise AnthropicProviderError("Anthropic response content block is invalid")
        if block.get("type") != "text":
            continue
        text = block.get("text")
        if not isinstance(text, str):
            raise AnthropicProviderError("Anthropic response text block is missing text")
        parts.append(text)
    if not parts:
        raise AnthropicProviderError("Anthropic response is missing text content")
    return "".join(parts)


def _from_anthropic_payload(
    payload: dict[str, Any],
    request: GenerationRequest,
) -> GenerationResponse:
    """Map an Anthropic Messages JSON payload to GenerationResponse."""
    try:
        response_id = payload.get("id")
        if not isinstance(response_id, str) or not response_id.strip():
            raise AnthropicProviderError("Anthropic response is missing a valid id")
        model = payload.get("model")
        if not isinstance(model, str) or not model.strip():
            model = request.model
        content = _text_from_content_blocks(payload.get("content"))
        usage_payload = payload.get("usage")
        usage: TokenUsage | None = None
        if isinstance(usage_payload, dict):
            input_tokens = usage_payload.get("input_tokens")
            output_tokens = usage_payload.get("output_tokens")
            if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
                raise AnthropicProviderError("Anthropic response usage is invalid")
            usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)
        return GenerationResponse(
            id=response_id,
            model=model,
            output=Message(role=MessageRole.ASSISTANT, content=content),
            usage=usage,
        )
    except AnthropicProviderError:
        raise
    except (KeyError, TypeError, ValueError) as err:
        raise AnthropicProviderError("Anthropic response payload is malformed") from err


class AnthropicModelProvider:
    """ModelProvider adapter for Anthropic Messages over HTTP."""

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient,
        base_url: str = _DEFAULT_ANTHROPIC_BASE_URL,
    ) -> None:
        if not api_key.strip():
            raise AnthropicProviderError("api_key must not be empty or blank")
        if not base_url.strip():
            raise AnthropicProviderError("base_url must not be empty or blank")
        self._api_key = api_key
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Invoke Anthropic Messages and return a GenerationResponse."""
        url = f"{self._base_url}/v1/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_API_VERSION,
            "Content-Type": "application/json",
        }
        body = _to_anthropic_body(request)
        try:
            response = await self._http_client.post(url, json=body, headers=headers)
        except httpx.HTTPError as err:
            raise AnthropicProviderError("Anthropic HTTP request failed") from err
        if response.status_code >= 400:
            raise AnthropicProviderError(f"Anthropic HTTP request failed with status {response.status_code}")
        try:
            payload = response.json()
        except ValueError as err:
            raise AnthropicProviderError("Anthropic response body is not valid JSON") from err
        if not isinstance(payload, dict):
            raise AnthropicProviderError("Anthropic response body must be a JSON object")
        return _from_anthropic_payload(payload, request)
