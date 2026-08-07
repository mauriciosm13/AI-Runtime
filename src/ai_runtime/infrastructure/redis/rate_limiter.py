"""Redis token-bucket rate limiter scoped per organization."""

import logging
import time
from collections.abc import Callable
from uuid import UUID
from redis.asyncio import Redis
from redis.exceptions import RedisError
from ai_runtime.ports.rate_limiter import RateLimitDecision

_LOGGER = logging.getLogger("ai_runtime.redis.rate_limiter")

# KEYS[1] = bucket hash
# ARGV[1] = capacity, ARGV[2] = refill_per_second, ARGV[3] = now, ARGV[4] = requested
_TOKEN_BUCKET_SCRIPT = """
local capacity = tonumber(ARGV[1])
local refill_per_second = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local data = redis.call('HMGET', KEYS[1], 'tokens', 'timestamp')
local tokens = tonumber(data[1])
local timestamp = tonumber(data[2])

if tokens == nil then
  tokens = capacity
  timestamp = now
end

local elapsed = math.max(0, now - timestamp)
tokens = math.min(capacity, tokens + (elapsed * refill_per_second))

local allowed = 0
local retry_after = 0
if tokens >= requested then
  tokens = tokens - requested
  allowed = 1
else
  local missing = requested - tokens
  retry_after = math.ceil(missing / refill_per_second)
end

redis.call('HSET', KEYS[1], 'tokens', tokens, 'timestamp', now)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / refill_per_second) + 1)
return {allowed, retry_after}
"""


class RedisRateLimiter:
    """Consume organization request budget via a Redis-backed token bucket."""

    def __init__(
        self,
        redis: Redis,
        *,
        requests_per_minute: int,
        burst: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis
        self._capacity = float(burst)
        self._refill_per_second = requests_per_minute / 60.0
        self._clock = clock
        self._script = self._redis.register_script(_TOKEN_BUCKET_SCRIPT)

    async def consume(self, organization_id: UUID) -> RateLimitDecision:
        """Consume one token for ``organization_id``, fail-open on Redis errors."""
        key = f"rl:org:{organization_id}"
        try:
            result = await self._script(
                keys=[key],
                args=[self._capacity, self._refill_per_second, self._clock(), 1],
            )
        except RedisError:
            _LOGGER.warning("rate_limit_redis_unavailable", exc_info=True)
            return RateLimitDecision(allowed=True)

        allowed = int(result[0]) == 1
        retry_after = int(result[1]) if not allowed else None
        return RateLimitDecision(allowed=allowed, retry_after_seconds=retry_after)
