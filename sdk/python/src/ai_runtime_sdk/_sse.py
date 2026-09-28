"""Parse the provider-neutral Server-Sent Events from POST /v1/responses."""

import json
from dataclasses import dataclass, field
from typing import Any
from pydantic import BaseModel, ConfigDict, ValidationError
from ai_runtime_sdk.errors import AIRuntimeError, error_from_body
from ai_runtime_sdk.models import Response, ResponseDelta


class _DeltaBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str


class _DeltaFrame(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    model: str
    delta: _DeltaBody


@dataclass
class SseParser:
    """Accumulate SSE lines until a blank line completes one event."""

    event: str = "message"
    data: list[str] = field(default_factory=list)

    def feed(self, line: str) -> tuple[str, str] | None:
        """Consume one line. Return ``(event, data)`` when a frame completes."""
        line = line.rstrip("\r")
        if line == "":
            return self._finish()
        if line.startswith(":"):
            return None
        field_name, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field_name == "event":
            self.event = value
        elif field_name == "data":
            self.data.append(value)
        return None

    def finish(self) -> tuple[str, str] | None:
        """Return a trailing frame that arrived without a closing blank line."""
        return self._finish()

    def _finish(self) -> tuple[str, str] | None:
        if not self.data:
            self.event = "message"
            return None
        payload = "\n".join(self.data)
        event = self.event
        self.event = "message"
        self.data = []
        return event, payload


def parse_stream_frame(event: str, data: str, *, request_id: str | None = None) -> ResponseDelta | Response:
    """Map one SSE frame to a delta, a completed response, or an error."""
    try:
        payload: Any = json.loads(data)
    except json.JSONDecodeError as err:
        raise AIRuntimeError(
            code="invalid_response",
            message="Stream event was not JSON.",
            status_code=200,
            request_id=request_id,
        ) from err
    if event == "response.error":
        raise error_from_body(payload, status_code=200, request_id=request_id, fallback_message="Stream failed.")
    if not isinstance(payload, dict):
        raise AIRuntimeError(
            code="invalid_response",
            message="Stream event was not a JSON object.",
            status_code=200,
            request_id=request_id,
        )
    try:
        if event == "response.delta":
            frame = _DeltaFrame.model_validate(payload)
            return ResponseDelta(id=frame.id, model=frame.model, content=frame.delta.content)
        if event == "response.completed":
            return Response.model_validate(payload)
    except ValidationError as err:
        raise AIRuntimeError(
            code="invalid_response",
            message="Stream event did not match the API contract.",
            status_code=200,
            request_id=request_id,
        ) from err
    raise AIRuntimeError(
        code="invalid_response",
        message=f"Unexpected stream event '{event}'.",
        status_code=200,
        request_id=request_id,
    )
