"""Gemini generateContent adapter implementing ModelProvider."""

from typing import Any
import httpx
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, Message, MessageRole, TokenUsage
from ai_runtime.providers.gemini.errors import GeminiProviderError

_DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"
_GEMINI_GENERATE_PATH = "/v1beta/models"


def _split_system_messages(request: GenerationRequest) -> tuple[str | None, list[Message]]:
    """Extract system messages for Gemini ``systemInstruction``; return the rest."""
    system_parts: list[str] = []
    conversation: list[Message] = []
    for message in request.messages:
        if message.role is MessageRole.SYSTEM:
            system_parts.append(message.content)
        else:
            conversation.append(message)
    system = "\n\n".join(system_parts) if system_parts else None
    return system, conversation


def _gemini_role(role: MessageRole) -> str:
    """Map a domain message role to a Gemini contents role."""
    if role is MessageRole.ASSISTANT:
        return "model"
    return role.value


def _to_gemini_body(request: GenerationRequest) -> dict[str, Any]:
    """Map a GenerationRequest to a Gemini generateContent JSON body."""
    system, conversation = _split_system_messages(request)
    if not conversation:
        raise GeminiProviderError("messages must contain at least one non-system message")
    body: dict[str, Any] = {
        "contents": [
            {"role": _gemini_role(message.role), "parts": [{"text": message.content}]}
            for message in conversation
        ],
    }
    if system is not None:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    generation_config: dict[str, Any] = {}
    if request.temperature is not None:
        generation_config["temperature"] = request.temperature
    if request.max_output_tokens is not None:
        generation_config["maxOutputTokens"] = request.max_output_tokens
    if generation_config:
        body["generationConfig"] = generation_config
    return body


def _text_from_parts(parts: object) -> str:
    """Join Gemini text parts into a single assistant string, skipping thoughts."""
    if not isinstance(parts, list) or not parts:
        raise GeminiProviderError("Gemini response is missing content parts")
    texts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            raise GeminiProviderError("Gemini response content part is invalid")
        if part.get("thought") is True:
            continue
        text = part.get("text")
        if text is None:
            continue
        if not isinstance(text, str):
            raise GeminiProviderError("Gemini response text part is missing text")
        texts.append(text)
    if not texts:
        raise GeminiProviderError("Gemini response is missing text content")
    return "".join(texts)


def _from_gemini_payload(
    payload: dict[str, Any],
    request: GenerationRequest,
) -> GenerationResponse:
    """Map a Gemini generateContent JSON payload to GenerationResponse."""
    try:
        response_id = payload.get("responseId")
        if not isinstance(response_id, str) or not response_id.strip():
            raise GeminiProviderError("Gemini response is missing a valid id")
        model = payload.get("modelVersion")
        if not isinstance(model, str) or not model.strip():
            model = request.model
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise GeminiProviderError("Gemini response is missing candidates")
        first_candidate = candidates[0]
        if not isinstance(first_candidate, dict):
            raise GeminiProviderError("Gemini response candidate is invalid")
        content = first_candidate.get("content")
        if not isinstance(content, dict):
            raise GeminiProviderError("Gemini response candidate is missing content")
        output_text = _text_from_parts(content.get("parts"))
        usage_payload = payload.get("usageMetadata")
        usage: TokenUsage | None = None
        if isinstance(usage_payload, dict):
            input_tokens = usage_payload.get("promptTokenCount")
            output_tokens = usage_payload.get("candidatesTokenCount")
            if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
                raise GeminiProviderError("Gemini response usage is invalid")
            usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)
        return GenerationResponse(
            id=response_id,
            model=model,
            output=Message(role=MessageRole.ASSISTANT, content=output_text),
            usage=usage,
        )
    except GeminiProviderError:
        raise
    except (KeyError, TypeError, ValueError) as err:
        raise GeminiProviderError("Gemini response payload is malformed") from err


class GeminiModelProvider:
    """ModelProvider adapter for Gemini generateContent over HTTP."""

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient,
        base_url: str = _DEFAULT_GEMINI_BASE_URL,
    ) -> None:
        if not api_key.strip():
            raise GeminiProviderError("api_key must not be empty or blank")
        if not base_url.strip():
            raise GeminiProviderError("base_url must not be empty or blank")
        self._api_key = api_key
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Invoke Gemini generateContent and return a GenerationResponse."""
        url = f"{self._base_url}{_GEMINI_GENERATE_PATH}/{request.model}:generateContent"
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        body = _to_gemini_body(request)
        try:
            response = await self._http_client.post(url, json=body, headers=headers)
        except httpx.HTTPError as err:
            raise GeminiProviderError.transient("Gemini HTTP request failed") from err
        if response.status_code >= 400:
            raise GeminiProviderError.from_http_status(
                f"Gemini HTTP request failed with status {response.status_code}",
                response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as err:
            raise GeminiProviderError("Gemini response body is not valid JSON") from err
        if not isinstance(payload, dict):
            raise GeminiProviderError("Gemini response body must be a JSON object")
        return _from_gemini_payload(payload, request)
