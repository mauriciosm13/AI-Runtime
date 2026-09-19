"""Unit tests for RedisResponseCache with an in-memory Redis stand-in."""

import asyncio
from uuid import uuid4
from redis.exceptions import RedisError
from ai_runtime.application.responses.cache_fingerprint import fingerprint_generation_request
from ai_runtime.domain.generation import GenerationRequest, Message, MessageRole
from ai_runtime.infrastructure.redis.response_cache import RedisResponseCache


class _MemoryRedis:
    """Minimal async Redis map for response-cache adapter tests."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expire: dict[str, int] = {}
        self.fail = False

    async def get(self, name: str) -> str | None:
        if self.fail:
            raise RedisError("redis unavailable")
        return self.values.get(name)

    async def set(self, name: str, value: str, ex: int | None = None) -> bool:
        if self.fail:
            raise RedisError("redis unavailable")
        self.values[name] = value
        if ex is not None:
            self.expire[name] = ex
        return True


def test_set_and_get_round_trip() -> None:
    """A stored payload is returned with the expected key and TTL."""
    redis = _MemoryRedis()
    cache = RedisResponseCache(redis, ttl_seconds=60)  # type: ignore[arg-type]
    org_id = uuid4()
    request = GenerationRequest(model="gpt-test", messages=(Message(role=MessageRole.USER, content="Hello"),))
    fingerprint = fingerprint_generation_request(request)
    asyncio.run(cache.set(org_id, fingerprint, '{"id":"r1"}'))
    assert redis.values[f"cache:resp:{org_id}:{fingerprint}"] == '{"id":"r1"}'
    assert redis.expire[f"cache:resp:{org_id}:{fingerprint}"] == 60
    assert asyncio.run(cache.get(org_id, fingerprint)) == '{"id":"r1"}'


def test_get_miss_returns_none() -> None:
    """Unknown keys are a miss."""
    cache = RedisResponseCache(_MemoryRedis(), ttl_seconds=60)  # type: ignore[arg-type]
    assert asyncio.run(cache.get(uuid4(), "missing")) is None


def test_get_and_set_fail_open_on_redis_error() -> None:
    """Redis errors behave like a miss and skip writes."""
    redis = _MemoryRedis()
    redis.fail = True
    cache = RedisResponseCache(redis, ttl_seconds=60)  # type: ignore[arg-type]
    org_id = uuid4()
    assert asyncio.run(cache.get(org_id, "abc")) is None
    asyncio.run(cache.set(org_id, "abc", "{}"))
