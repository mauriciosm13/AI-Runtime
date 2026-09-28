# AI Runtime Python SDK

Client for the AI Runtime HTTP API. Applications install this package instead of the server.

```bash
pip install -e sdk/python
```

```python
from ai_runtime_sdk import AIRuntime

with AIRuntime(api_key="airt_...", base_url="http://127.0.0.1:8000") as client:
    response = client.responses.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(response.output.content)

    for event in client.responses.stream(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
    ):
        print(event)
```

`AsyncAIRuntime` has the same `responses` and `prompts` resources for asyncio.

`responses.create` sends `POST /v1/responses`. Pass exactly one of `messages` or `prompt`. `idempotency_key` maps to `Idempotency-Key`. `responses.stream` sets `stream: true` and yields `ResponseDelta` values, then a `Response`. A `response.error` event raises `AIRuntimeError`.

`prompts.create` and `prompts.list` call `POST /v1/prompts` and `GET /v1/prompts/{name}`.

The API key is sent as `Authorization: Bearer`. It is omitted from `repr` and from error messages.
