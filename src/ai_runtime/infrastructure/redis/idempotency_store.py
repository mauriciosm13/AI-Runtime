"""Redis adapter for organization-scoped Idempotency-Key records."""

import logging
from uuid import UUID
from redis.asyncio import Redis
from redis.exceptions import RedisError
from ai_runtime.ports.idempotency_store import IdempotencyBeginResult, IdempotencyCompleted, IdempotencyInProgress, IdempotencyMiss

_LOGGER = logging.getLogger("ai_runtime.redis.idempotency")
_STATUS_IN_PROGRESS = "in_progress"
_STATUS_COMPLETED = "completed"


class RedisIdempotencyStore:
    """Store in-progress leases and completed response payloads in Redis."""

    def __init__(self, redis: Redis, *, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    def _key(self, organization_id: UUID, key: str) -> str:
        return f"idem:{organization_id}:{key}"

    async def begin(self, organization_id: UUID, key: str) -> IdempotencyBeginResult:
        """Claim the key, detect in-flight conflicts, or return a completed payload.

        Fail-open: Redis errors behave like a miss so the request may proceed.
        """
        redis_key = self._key(organization_id, key)
        try:
            claimed = await self._redis.set(
                redis_key,
                _STATUS_IN_PROGRESS,
                nx=True,
                ex=self._ttl_seconds,
            )
            if claimed:
                return IdempotencyMiss()

            raw = await self._redis.get(redis_key)
        except RedisError:
            _LOGGER.warning("idempotency_redis_unavailable", exc_info=True)
            return IdempotencyMiss()

        if raw is None:
            return IdempotencyMiss()
        existing = raw if isinstance(raw, str) else raw.decode()
        if existing == _STATUS_IN_PROGRESS:
            return IdempotencyInProgress()
        completed_prefix = f"{_STATUS_COMPLETED}:"
        if existing.startswith(completed_prefix):
            return IdempotencyCompleted(payload=existing.removeprefix(completed_prefix))
        return IdempotencyInProgress()

    async def complete(self, organization_id: UUID, key: str, payload: str) -> None:
        """Persist the completed payload for replay within the configured TTL."""
        redis_key = self._key(organization_id, key)
        try:
            await self._redis.set(
                redis_key,
                f"{_STATUS_COMPLETED}:{payload}",
                ex=self._ttl_seconds,
            )
        except RedisError:
            _LOGGER.warning("idempotency_complete_redis_unavailable", exc_info=True)

    async def release(self, organization_id: UUID, key: str) -> None:
        """Delete an in-progress lease after a failed attempt."""
        redis_key = self._key(organization_id, key)
        try:
            current = await self._redis.get(redis_key)
            current_value = None if current is None else (current if isinstance(current, str) else current.decode())
            if current_value == _STATUS_IN_PROGRESS:
                await self._redis.delete(redis_key)
        except RedisError:
            _LOGGER.warning("idempotency_release_redis_unavailable", exc_info=True)
