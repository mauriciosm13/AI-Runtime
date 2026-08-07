"""Factory for the shared async Redis client."""

from redis.asyncio import Redis


def create_redis_client(redis_url: str) -> Redis:
    """Create an async Redis client from a redis:// or rediss:// URL."""
    return Redis.from_url(redis_url, decode_responses=True)
