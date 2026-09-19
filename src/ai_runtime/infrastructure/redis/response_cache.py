"""Redis adapter for organization-scoped response cache payloads."""

import logging
from uuid import UUID
from redis.asyncio import Redis
from redis.exceptions import RedisError

_LOGGER = logging.getLogger("ai_runtime.redis.response_cache")


class RedisResponseCache:
    """Store opted-in generation responses in Redis with a bounded TTL."""

    def __init__(self, redis: Redis, *, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    def _key(self, organization_id: UUID, fingerprint: str) -> str:
        return f"cache:resp:{organization_id}:{fingerprint}"

    async def get(self, organization_id: UUID, fingerprint: str) -> str | None:
        """Return the cached payload, or None on miss or Redis failure."""
        try:
            raw = await self._redis.get(self._key(organization_id, fingerprint))
        except RedisError:
            _LOGGER.warning("response_cache_get_redis_unavailable", exc_info=True)
            return None
        if raw is None:
            return None
        return raw if isinstance(raw, str) else raw.decode()

    async def set(self, organization_id: UUID, fingerprint: str, payload: str) -> None:
        """Write the payload with the configured TTL. Fail open on Redis errors."""
        try:
            await self._redis.set(self._key(organization_id, fingerprint), payload, ex=self._ttl_seconds)
        except RedisError:
            _LOGGER.warning("response_cache_set_redis_unavailable", exc_info=True)
