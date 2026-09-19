"""Stable content hash for opt-in response cache keys."""

import hashlib
import json
from ai_runtime.domain.generation import GenerationRequest


def fingerprint_generation_request(request: GenerationRequest) -> str:
    """Return a SHA-256 hex digest of the cacheable request fields."""
    payload = {
        "max_output_tokens": request.max_output_tokens,
        "messages": [
            {
                "content": message.content,
                "name": message.name,
                "role": message.role.value,
                "tool_call_id": message.tool_call_id,
                "tool_calls": [{"arguments": call.arguments, "id": call.id, "name": call.name} for call in message.tool_calls],
            }
            for message in request.messages
        ],
        "model": request.model,
        "temperature": request.temperature,
        "tools": [{"description": tool.description, "name": tool.name, "parameters": tool.parameters} for tool in request.tools],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
