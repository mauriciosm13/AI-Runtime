"""Unit tests for the ResponseCache port contract."""

import asyncio
from uuid import UUID, uuid4
from ai_runtime.ports.response_cache import ResponseCache


class FakeResponseCache:
    """In-memory stand-in that satisfies ResponseCache."""

    async def get(self, organization_id: UUID, fingerprint: str) -> str | None:
        _ = organization_id, fingerprint
        return None

    async def set(self, organization_id: UUID, fingerprint: str, payload: str) -> None:
        _ = organization_id, fingerprint, payload


def test_fake_response_cache_satisfies_contract() -> None:
    """A structural fake is accepted as ResponseCache."""
    cache: ResponseCache = FakeResponseCache()
    assert isinstance(cache, ResponseCache)
    assert asyncio.run(cache.get(uuid4(), "abc")) is None
    asyncio.run(cache.set(uuid4(), "abc", "{}"))
