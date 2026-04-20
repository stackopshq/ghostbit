"""Unit tests for RedisStorage branches that don't need a live broker.

A full integration test suite against Redis is out of scope for local
pytest runs; these tests mock the asyncio client just enough to exercise
behaviours that are easy to get wrong (e.g. the already-expired save path).
"""

from unittest.mock import AsyncMock

import pytest

from app.storage.base import PasteData
from app.storage.redis_backend import RedisStorage


def _paste(**overrides) -> PasteData:
    base = {
        "id": "x",
        "content": "Y2lwaGVydGV4dA==",
        "nonce": "bm9uY2UxMjM0NTY=",
        "kdf_salt": None,
        "language": None,
        "created_at": 1_700_000_000,
        "expires_at": None,
        "burn": False,
        "has_password": False,
        "delete_token_hash": "0" * 64,
    }
    base.update(overrides)
    return PasteData(**base)


@pytest.mark.anyio
async def test_save_rejects_already_expired_paste():
    """`save()` on a paste whose expires_at is in the past must return False
    and MUST NOT call redis.set. Previously returned True, making the admin
    import count an import that never hit the backend."""
    storage = RedisStorage("redis://localhost")
    storage._client = AsyncMock()

    result = await storage.save(_paste(id="exp", expires_at=1))  # epoch=1
    assert result is False
    storage._client.set.assert_not_called()


@pytest.mark.anyio
async def test_save_persists_paste_with_future_ttl():
    """Sanity check that the TTL path still writes with the expected args."""
    import time

    storage = RedisStorage("redis://localhost")
    storage._client = AsyncMock()
    storage._client.set.return_value = True

    future = int(time.time()) + 3600
    result = await storage.save(_paste(id="ok", expires_at=future))
    assert result is True
    assert storage._client.set.await_count == 1
    _args, kwargs = storage._client.set.call_args
    assert kwargs["nx"] is True
    assert 0 < kwargs["ex"] <= 3600
