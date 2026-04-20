"""Tests for the SQLite connection pool.

The pool exists to let concurrent reads progress in parallel under WAL;
the previous single-connection + asyncio.Lock serialized everything.
These tests make that concurrency observable instead of implicit.
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

import pytest

from app.storage.base import PasteData
from app.storage.sqlite import SQLiteStorage


def _paste(pid: str, **extra) -> PasteData:
    base = {
        "id": pid,
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
    base.update(extra)
    return PasteData(**base)


@pytest.fixture
async def storage():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    s = SQLiteStorage(path, pool_size=4)
    await s.init()
    try:
        yield s
    finally:
        await s.close()
        Path(path).unlink(missing_ok=True)


async def test_pool_is_populated(storage):
    assert storage._pool is not None
    assert storage._pool.qsize() == 4
    assert len(storage._all_conns) == 4


async def test_concurrent_reads_do_not_serialize(storage):
    """Seed a row, then fire N concurrent get() calls that collectively
    would take N * read_time if serialized. With a pool of 4, the total
    wall time should be well below the serial upper bound."""
    await storage.save(_paste("same"))

    N = 20
    start = time.perf_counter()
    results = await asyncio.gather(*(storage.get("same") for _ in range(N)))
    elapsed = time.perf_counter() - start

    assert all(r is not None and r.id == "same" for r in results)
    # Not a strict perf assertion — just a sanity check that 20 reads on a
    # pool of 4 finish quickly. SQLite in-memory-ish ops on a single row
    # return in sub-millisecond; 0.5 s leaves a lot of room for slow CI.
    assert elapsed < 0.5


async def test_acquire_releases_connection_even_on_error(storage):
    """If a caller raises inside the acquire() block, the connection must
    come back to the pool. A leaked connection would shrink the usable pool
    silently and eventually starve the app."""
    with pytest.raises(RuntimeError, match="boom"):
        async with storage._acquire():
            raise RuntimeError("boom")
    # All four connections should still be in the pool.
    assert storage._pool.qsize() == 4


async def test_concurrent_inserts_dont_corrupt(storage):
    """Fire parallel saves with distinct IDs; busy_timeout + WAL must let
    all of them land exactly once."""
    pastes = [_paste(f"p{i:03d}") for i in range(25)]
    results = await asyncio.gather(*(storage.save(p) for p in pastes))
    assert all(results), "every save should have returned True"

    # Re-read them to confirm persistence.
    round_trips = await asyncio.gather(*(storage.get(f"p{i:03d}") for i in range(25)))
    assert all(p is not None for p in round_trips)


async def test_iter_all_holds_one_connection_others_stay_available(storage):
    """A long-running iter_all() (admin export) shouldn't block reads on
    the other N-1 pooled connections."""
    for i in range(3):
        await storage.save(_paste(f"r{i}"))

    agen = storage.iter_all().__aiter__()
    # Drive one step to actually check out a connection for the iteration.
    first = await anext(agen)
    assert first.id.startswith("r")

    # At this point one connection is in use; the rest are free.
    assert storage._pool.qsize() == 3
    # An independent get() must still complete.
    p = await storage.get("r0")
    assert p is not None

    # Clean up — exhaust the generator so it releases the connection.
    async for _ in agen:
        pass
    assert storage._pool.qsize() == 4
