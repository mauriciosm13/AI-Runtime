"""Unit tests for RedisRateLimiter, including real Lua token-bucket behavior."""

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis
from redis.exceptions import RedisError
from ai_runtime.infrastructure.redis.rate_limiter import RedisRateLimiter

_ScriptRunner = Callable[..., Awaitable[list[int]]]


class _BoomRedis:
    """Redis stand-in whose registered script always fails."""

    def register_script(self, _script: str) -> _ScriptRunner:
        async def _run(*, keys: list[str], args: list[object]) -> list[int]:
            _ = keys, args
            raise RedisError("redis unavailable")

        return _run


class _ScriptRedis:
    """Redis stand-in that returns a fixed script result."""

    def __init__(self, result: list[int]) -> None:
        self._result = result

    def register_script(self, _script: str) -> _ScriptRunner:
        async def _run(*, keys: list[str], args: list[object]) -> list[int]:
            _ = keys, args
            return self._result

        return _run


class _FrozenClock:
    """Mutable clock for deterministic refill tests."""

    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _limiter(
    redis: Redis,
    *,
    requests_per_minute: int,
    burst: int,
    clock: Callable[[], float],
) -> RedisRateLimiter:
    return RedisRateLimiter(
        redis,
        requests_per_minute=requests_per_minute,
        burst=burst,
        clock=clock,
    )


async def _consume_n(limiter: RedisRateLimiter, organization_id: UUID, n: int) -> list[bool]:
    allowed: list[bool] = []
    for _ in range(n):
        decision = await limiter.consume(organization_id)
        allowed.append(decision.allowed)
    return allowed


def test_rate_limiter_fails_open_when_redis_errors() -> None:
    """Redis errors allow the request and do not raise to callers."""
    limiter = RedisRateLimiter(_BoomRedis(), requests_per_minute=60, burst=60)  # type: ignore[arg-type]
    decision = asyncio.run(limiter.consume(uuid4()))
    assert decision.allowed is True
    assert decision.retry_after_seconds is None


def test_rate_limiter_maps_denied_script_result() -> None:
    """A denied Lua result becomes an allowed=False decision with retry_after."""
    limiter = RedisRateLimiter(_ScriptRedis([0, 9]), requests_per_minute=60, burst=60)  # type: ignore[arg-type]
    decision = asyncio.run(limiter.consume(uuid4()))
    assert decision.allowed is False
    assert decision.retry_after_seconds == 9


def test_rate_limiter_maps_allowed_script_result() -> None:
    """An allowed Lua result becomes allowed=True without retry_after."""
    limiter = RedisRateLimiter(_ScriptRedis([1, 0]), requests_per_minute=60, burst=60)  # type: ignore[arg-type]
    decision = asyncio.run(limiter.consume(uuid4()))
    assert decision.allowed is True
    assert decision.retry_after_seconds is None


def test_token_bucket_allows_burst_then_denies() -> None:
    """Lua token bucket allows up to burst requests, then denies the next one."""

    async def _run() -> None:
        redis = FakeAsyncRedis(decode_responses=True)
        clock = _FrozenClock(1_000.0)
        limiter = _limiter(redis, requests_per_minute=60, burst=3, clock=clock)
        org_id = uuid4()

        allowed = await _consume_n(limiter, org_id, 3)
        assert allowed == [True, True, True]

        denied = await limiter.consume(org_id)
        assert denied.allowed is False
        assert denied.retry_after_seconds == 1

        await redis.aclose()

    asyncio.run(_run())


def test_token_bucket_refills_after_elapsed_time() -> None:
    """After enough clock advancement, a previously empty bucket allows again."""

    async def _run() -> None:
        redis = FakeAsyncRedis(decode_responses=True)
        clock = _FrozenClock(1_000.0)
        # 60 rpm => 1 token/second; burst 2.
        limiter = _limiter(redis, requests_per_minute=60, burst=2, clock=clock)
        org_id = uuid4()

        assert (await _consume_n(limiter, org_id, 2)) == [True, True]
        assert (await limiter.consume(org_id)).allowed is False

        clock.advance(1.0)
        refilled = await limiter.consume(org_id)
        assert refilled.allowed is True
        assert refilled.retry_after_seconds is None

        assert (await limiter.consume(org_id)).allowed is False
        await redis.aclose()

    asyncio.run(_run())


def test_token_bucket_refill_is_capped_at_burst() -> None:
    """Refill never accumulates tokens above the configured burst capacity."""

    async def _run() -> None:
        redis = FakeAsyncRedis(decode_responses=True)
        clock = _FrozenClock(1_000.0)
        limiter = _limiter(redis, requests_per_minute=60, burst=2, clock=clock)
        org_id = uuid4()

        assert (await _consume_n(limiter, org_id, 2)) == [True, True]
        clock.advance(120.0)

        # Cap at burst=2 even after a long idle refill window.
        assert (await _consume_n(limiter, org_id, 2)) == [True, True]
        assert (await limiter.consume(org_id)).allowed is False
        await redis.aclose()

    asyncio.run(_run())


def test_token_bucket_is_scoped_per_organization() -> None:
    """Exhausting one organization bucket does not affect another organization."""

    async def _run() -> None:
        redis = FakeAsyncRedis(decode_responses=True)
        clock = _FrozenClock(1_000.0)
        limiter = _limiter(redis, requests_per_minute=60, burst=1, clock=clock)
        org_a = uuid4()
        org_b = uuid4()

        assert (await limiter.consume(org_a)).allowed is True
        assert (await limiter.consume(org_a)).allowed is False
        assert (await limiter.consume(org_b)).allowed is True
        await redis.aclose()

    asyncio.run(_run())


def test_token_bucket_retry_after_reflects_missing_tokens() -> None:
    """retry_after_seconds is ceil(missing_tokens / refill_rate)."""

    async def _run() -> None:
        redis = FakeAsyncRedis(decode_responses=True)
        clock = _FrozenClock(1_000.0)
        # 30 rpm => 0.5 tokens/second; burst 1.
        limiter = _limiter(redis, requests_per_minute=30, burst=1, clock=clock)
        org_id = uuid4()

        assert (await limiter.consume(org_id)).allowed is True
        denied = await limiter.consume(org_id)
        assert denied.allowed is False
        assert denied.retry_after_seconds == 2
        await redis.aclose()

    asyncio.run(_run())
