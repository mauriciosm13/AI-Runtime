"""Gemini generateContent adapter implementing ModelProvider."""

from collections.abc import AsyncIterator
from typing import Any
import json
import httpx
from ai_runtime.domain.generation import GenerationDelta, GenerationRequest, GenerationResponse
from ai_runtime.domain.generation import Message, MessageRole, TokenUsage, ToolCall
from ai_runtime.providers.gemini.errors import GeminiProviderError
from ai_runtime.providers.sse import iter_sse_events

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
    if role is MessageRole.TOOL:
        return "user"
    return role.value


def _gemini_parts(message: Message) -> list[dict[str, Any]]:
    """Map a domain message to Gemini content parts."""
    if message.role is MessageRole.TOOL:
        name = message.name if message.name is not None and message.name.strip() else message.tool_call_id
        assert name is not None
        try:
            payload = json.loads(message.content)
        except json.JSONDecodeError:
            payload = {"result": message.content}
        if not isinstance(payload, dict):
            payload = {"result": message.content}
        return [{"functionResponse": {"name": name, "response": payload}}]
    if message.tool_calls:
        parts: list[dict[str, Any]] = []
        if message.content.strip():
            parts.append({"text": message.content})
        for call in message.tool_calls:
            try:
                args = json.loads(call.arguments)
            except json.JSONDecodeError as err:
                raise GeminiProviderError("tool call arguments must be valid JSON") from err
            if not isinstance(args, dict):
                raise GeminiProviderError("tool call arguments must be a JSON object")
            parts.append({"functionCall": {"name": call.name, "args": args}})
        return parts
    return [{"text": message.content}]


def _to_gemini_body(request: GenerationRequest) -> dict[str, Any]:
    """Map a GenerationRequest to a Gemini generateContent JSON body."""
    system, conversation = _split_system_messages(request)
    if not conversation:
        raise GeminiProviderError("messages must contain at least one non-system message")
    body: dict[str, Any] = {
        "contents": [{"role": _gemini_role(message.role), "parts": _gemini_parts(message)} for message in conversation],
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
    if request.tools:
        body["tools"] = [
            {
                "functionDeclarations": [
                    {"name": tool.name, "description": tool.description, "parameters": tool.parameters} for tool in request.tools
                ]
            }
        ]
    return body


def _tool_calls_from_gemini(parts: object) -> tuple[ToolCall, ...]:
    """Parse Gemini functionCall parts into domain ToolCall values."""
    if not isinstance(parts, list):
        return ()
    calls: list[ToolCall] = []
    for index, part in enumerate(parts):
        if not isinstance(part, dict) or "functionCall" not in part:
            continue
        function_call = part.get("functionCall")
        if not isinstance(function_call, dict):
            raise GeminiProviderError("Gemini response functionCall is invalid")
        name = function_call.get("name")
        args = function_call.get("args")
        if not isinstance(name, str) or not isinstance(args, dict):
            raise GeminiProviderError("Gemini response functionCall is invalid")
        calls.append(
            ToolCall(
                id=f"call_{index}_{name}",
                name=name,
                arguments=json.dumps(args, separators=(",", ":"), ensure_ascii=True),
            )
        )
    return tuple(calls)


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


def _optional_text_from_parts(parts: object) -> str:
    """Join Gemini text parts for a stream chunk; thought-only chunks yield empty text."""
    if not isinstance(parts, list) or not parts:
        return ""
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
        parts = content.get("parts")
        output_text = _optional_text_from_parts(parts)
        tool_calls = _tool_calls_from_gemini(parts)
        if not output_text.strip() and not tool_calls:
            raise GeminiProviderError("Gemini response is missing text content")
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
            output=Message(role=MessageRole.ASSISTANT, content=output_text, tool_calls=tool_calls),
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

    async def stream(self, request: GenerationRequest) -> AsyncIterator[GenerationDelta | GenerationResponse]:
        """Invoke Gemini streamGenerateContent and yield domain events."""
        url = f"{self._base_url}{_GEMINI_GENERATE_PATH}/{request.model}:streamGenerateContent"
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        body = _to_gemini_body(request)
        try:
            async with self._http_client.stream("POST", url, params={"alt": "sse"}, json=body, headers=headers) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise GeminiProviderError.from_http_status(
                        f"Gemini HTTP request failed with status {response.status_code}",
                        response.status_code,
                    )
                response_id = ""
                model = request.model
                assembled: list[str] = []
                usage: TokenUsage | None = None
                async for _event_name, data in iter_sse_events(response):
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError as err:
                        raise GeminiProviderError("Gemini stream chunk is not valid JSON") from err
                    if not isinstance(payload, dict):
                        raise GeminiProviderError("Gemini stream chunk must be a JSON object")
                    chunk_id = payload.get("responseId")
                    if isinstance(chunk_id, str) and chunk_id.strip():
                        response_id = chunk_id
                    chunk_model = payload.get("modelVersion")
                    if isinstance(chunk_model, str) and chunk_model.strip():
                        model = chunk_model
                    candidates = payload.get("candidates")
                    if isinstance(candidates, list) and candidates:
                        first_candidate = candidates[0]
                        if not isinstance(first_candidate, dict):
                            raise GeminiProviderError("Gemini stream candidate is invalid")
                        content = first_candidate.get("content")
                        if isinstance(content, dict):
                            text = _optional_text_from_parts(content.get("parts"))
                            if text:
                                if not response_id.strip():
                                    raise GeminiProviderError("Gemini stream is missing a valid id")
                                assembled.append(text)
                                yield GenerationDelta(id=response_id, model=model, content=text)
                    usage_payload = payload.get("usageMetadata")
                    if isinstance(usage_payload, dict):
                        input_tokens = usage_payload.get("promptTokenCount")
                        output_tokens = usage_payload.get("candidatesTokenCount")
                        if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                            usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)
                        elif input_tokens is not None or output_tokens is not None:
                            raise GeminiProviderError("Gemini response usage is invalid")
        except GeminiProviderError:
            raise
        except httpx.HTTPError as err:
            raise GeminiProviderError.transient("Gemini HTTP request failed") from err
        if not response_id.strip():
            raise GeminiProviderError("Gemini stream is missing a valid id")
        yield GenerationResponse(
            id=response_id,
            model=model,
            output=Message(role=MessageRole.ASSISTANT, content="".join(assembled)),
            usage=usage,
        )
