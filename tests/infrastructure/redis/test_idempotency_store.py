"""Unit tests for RedisIdempotencyStore with an in-memory Redis stand-in."""

import asyncio
from uuid import uuid4
from redis.exceptions import RedisError
from ai_runtime.infrastructure.redis.idempotency_store import RedisIdempotencyStore
from ai_runtime.ports.idempotency_store import IdempotencyCompleted, IdempotencyInProgress, IdempotencyMiss


class _MemoryRedis:
    """Minimal async Redis hash map for idempotency adapter tests."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail = False

    async def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        _ = ex
        if self.fail:
            raise RedisError("redis unavailable")
        if nx and name in self.values:
            return None
        self.values[name] = value
        return True

    async def get(self, name: str) -> str | None:
        if self.fail:
            raise RedisError("redis unavailable")
        return self.values.get(name)

    async def delete(self, name: str) -> int:
        if self.fail:
            raise RedisError("redis unavailable")
        return 1 if self.values.pop(name, None) is not None else 0


def test_begin_claims_missing_key() -> None:
    """First begin claims the key and returns Miss."""
    redis = _MemoryRedis()
    store = RedisIdempotencyStore(redis, ttl_seconds=60)  # type: ignore[arg-type]
    org_id = uuid4()
    result = asyncio.run(store.begin(org_id, "k1"))
    assert isinstance(result, IdempotencyMiss)
    assert redis.values[f"idem:{org_id}:k1"] == "in_progress"


def test_begin_reports_in_progress() -> None:
    """A second begin against an in-progress key returns InProgress."""
    redis = _MemoryRedis()
    store = RedisIdempotencyStore(redis, ttl_seconds=60)  # type: ignore[arg-type]
    org_id = uuid4()
    asyncio.run(store.begin(org_id, "k1"))
    result = asyncio.run(store.begin(org_id, "k1"))
    assert isinstance(result, IdempotencyInProgress)


def test_complete_and_replay() -> None:
    """Completed payloads are returned by a later begin."""
    redis = _MemoryRedis()
    store = RedisIdempotencyStore(redis, ttl_seconds=60)  # type: ignore[arg-type]
    org_id = uuid4()
    asyncio.run(store.begin(org_id, "k1"))
    asyncio.run(store.complete(org_id, "k1", '{"id":"r1"}'))
    result = asyncio.run(store.begin(org_id, "k1"))
    assert isinstance(result, IdempotencyCompleted)
    assert result.payload == '{"id":"r1"}'


def test_release_removes_in_progress_lease() -> None:
    """Release deletes only in-progress values so retries can reclaim the key."""
    redis = _MemoryRedis()
    store = RedisIdempotencyStore(redis, ttl_seconds=60)  # type: ignore[arg-type]
    org_id = uuid4()
    asyncio.run(store.begin(org_id, "k1"))
    asyncio.run(store.release(org_id, "k1"))
    assert f"idem:{org_id}:k1" not in redis.values
    result = asyncio.run(store.begin(org_id, "k1"))
    assert isinstance(result, IdempotencyMiss)


def test_begin_fails_open_on_redis_error() -> None:
    """Redis errors during begin behave like a miss."""
    redis = _MemoryRedis()
    redis.fail = True
    store = RedisIdempotencyStore(redis, ttl_seconds=60)  # type: ignore[arg-type]
    result = asyncio.run(store.begin(uuid4(), "k1"))
    assert isinstance(result, IdempotencyMiss)
