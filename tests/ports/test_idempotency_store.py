"""Unit tests for the IdempotencyStore port contract."""

import asyncio
import json
from uuid import UUID, uuid4
from ai_runtime.ports.idempotency_store import IdempotencyBeginResult, IdempotencyMiss, IdempotencyStore


class FakeIdempotencyStore:
    """In-memory stand-in that satisfies IdempotencyStore."""

    async def begin(self, organization_id: UUID, key: str) -> IdempotencyBeginResult:
        _ = organization_id, key
        return IdempotencyMiss()

    async def complete(self, organization_id: UUID, key: str, payload: str) -> None:
        _ = organization_id, key, payload

    async def release(self, organization_id: UUID, key: str) -> None:
        _ = organization_id, key


def test_fake_idempotency_store_satisfies_contract() -> None:
    """A structural fake is accepted as IdempotencyStore."""
    store: IdempotencyStore = FakeIdempotencyStore()
    assert isinstance(store, IdempotencyStore)
    result = asyncio.run(store.begin(uuid4(), "key-1"))
    assert isinstance(result, IdempotencyMiss)
    asyncio.run(store.complete(uuid4(), "key-1", json.dumps({}, separators=(",", ":"), ensure_ascii=True)))
    asyncio.run(store.release(uuid4(), "key-1"))
