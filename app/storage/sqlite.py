import asyncio
import contextlib
import hashlib
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from .. import metrics
from ..config import settings
from .base import PasteData, StorageBackend

_log = logging.getLogger("ghostbit.storage.sqlite")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS pastes (
    id                TEXT PRIMARY KEY,
    content           TEXT NOT NULL,
    nonce             TEXT NOT NULL,
    kdf_salt          TEXT,
    language          TEXT,
    created_at        INTEGER NOT NULL,
    expires_at        INTEGER,
    burn              INTEGER NOT NULL DEFAULT 0,
    has_password      INTEGER NOT NULL DEFAULT 0,
    delete_token_hash TEXT NOT NULL,
    max_views         INTEGER,
    view_count        INTEGER NOT NULL DEFAULT 0,
    webhook_url       TEXT
)
"""

# column_name -> DDL snippet for ALTER TABLE
_EXPECTED_COLUMNS = {
    "max_views": "INTEGER",
    "view_count": "INTEGER NOT NULL DEFAULT 0",
    "webhook_url": "TEXT",
}


async def _configure_connection(conn: aiosqlite.Connection) -> None:
    """Apply per-connection PRAGMAs. journal_mode=WAL persists at the DB file
    level (applied once by the first connection); the others are connection-
    scoped, so every pool member has to set them."""
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    # busy_timeout lets a blocked writer wait up to 5 s for the WAL lock
    # instead of raising SQLITE_BUSY immediately. Without this, two
    # near-simultaneous write transactions on different connections fail
    # instead of queuing — defeats the whole point of the pool.
    await conn.execute("PRAGMA busy_timeout=5000")


class SQLiteStorage(StorageBackend):
    """SQLite backend with a fixed-size connection pool.

    Prior version held a single connection + an asyncio.Lock serializing
    every access. That's simple but caps throughput at one query at a
    time, which turned into a visible bottleneck under concurrent reads.

    WAL mode supports parallel readers + one writer. The pool lets the
    asyncio loop dispatch independent reads to independent connections,
    while SQLite itself serializes writers via its internal lock
    (complemented by busy_timeout so contenders queue instead of failing).
    Multi-statement transactions still run on a single checked-out
    connection — acquire() is a context manager that keeps the same
    connection from `await` to return.
    """

    def __init__(self, path: str, pool_size: int | None = None) -> None:
        self.path = path
        self._pool_size = pool_size if pool_size is not None else settings.sqlite_pool_size
        self._pool: asyncio.Queue[aiosqlite.Connection] | None = None
        self._all_conns: list[aiosqlite.Connection] = []
        self._cleanup_task: asyncio.Task | None = None

    async def init(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._pool = asyncio.Queue(maxsize=self._pool_size)

        for _ in range(self._pool_size):
            conn = await aiosqlite.connect(self.path)
            await _configure_connection(conn)
            self._all_conns.append(conn)
            self._pool.put_nowait(conn)

        # Schema bootstrap and migration use one pooled connection.
        async with self._acquire() as db:
            await db.execute(_CREATE_TABLE)
            existing = await self._column_names(db, "pastes")
            for col, ddl in _EXPECTED_COLUMNS.items():
                if col not in existing:
                    await db.execute(f"ALTER TABLE pastes ADD COLUMN {col} {ddl}")
            await db.commit()

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    @asynccontextmanager
    async def _acquire(self) -> AsyncIterator[aiosqlite.Connection]:
        """Check out a connection for the lifetime of an `async with` block.

        Records the wait time in the Prometheus histogram so an operator can
        see whether the pool is sized appropriately. A hot P99 on this one
        metric is the signal to bump SQLITE_POOL_SIZE.
        """
        assert self._pool is not None, "SQLiteStorage.init() not called"
        t0 = time.perf_counter()
        conn = await self._pool.get()
        metrics.sqlite_pool_wait_seconds.observe(time.perf_counter() - t0)
        try:
            yield conn
        finally:
            self._pool.put_nowait(conn)

    async def _column_names(self, db: aiosqlite.Connection, table: str) -> set[str]:
        async with db.execute(f"PRAGMA table_info({table})") as cursor:
            rows = await cursor.fetchall()
        return {row[1] for row in rows}

    async def save(self, paste: PasteData) -> bool:
        async with self._acquire() as db:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO pastes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    paste.id,
                    paste.content,
                    paste.nonce,
                    paste.kdf_salt,
                    paste.language,
                    paste.created_at,
                    paste.expires_at,
                    int(paste.burn),
                    int(paste.has_password),
                    paste.delete_token_hash,
                    paste.max_views,
                    paste.view_count,
                    paste.webhook_url,
                ),
            )
            await db.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_paste(row: aiosqlite.Row) -> PasteData:
        return PasteData(
            id=row["id"],
            content=row["content"],
            nonce=row["nonce"],
            kdf_salt=row["kdf_salt"],
            language=row["language"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            burn=bool(row["burn"]),
            has_password=bool(row["has_password"]),
            delete_token_hash=row["delete_token_hash"],
            max_views=row["max_views"],
            view_count=row["view_count"] or 0,
            webhook_url=row["webhook_url"],
        )

    async def get(self, paste_id: str) -> PasteData | None:
        async with (
            self._acquire() as db,
            db.execute("SELECT * FROM pastes WHERE id = ?", (paste_id,)) as cursor,
        ):
            row = await cursor.fetchone()
        return None if row is None else self._row_to_paste(row)

    async def increment_and_check_burn(self, paste_id: str) -> tuple[int | None, bool]:
        async with self._acquire() as db:
            # Multi-statement transaction: increment, then optionally delete.
            # Stays on a single connection for the whole block, so the
            # BEGIN IMMEDIATE…COMMIT pair is atomic wrt other pool users.
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "UPDATE pastes SET view_count = view_count + 1 "
                "WHERE id = ? "
                "RETURNING view_count, burn, max_views",
                (paste_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if row is None:
                await db.commit()
                return None, False
            view_count, burn, max_views = row["view_count"], row["burn"], row["max_views"]
            should_burn = bool(burn) or (max_views is not None and view_count >= max_views)
            if should_burn:
                await db.execute("DELETE FROM pastes WHERE id = ?", (paste_id,))
            await db.commit()
            return view_count, should_burn

    async def delete(self, paste_id: str, delete_token: str) -> bool:
        token_hash = hashlib.sha256(delete_token.encode()).hexdigest()
        async with self._acquire() as db:
            cursor = await db.execute(
                "DELETE FROM pastes WHERE id = ? AND delete_token_hash = ?",
                (paste_id, token_hash),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def force_delete(self, paste_id: str) -> None:
        async with self._acquire() as db:
            await db.execute("DELETE FROM pastes WHERE id = ?", (paste_id,))
            await db.commit()

    async def iter_all(self) -> AsyncIterator[PasteData]:
        # Streams via fetchmany(500) to avoid materializing a huge DB in
        # memory. Keeps the connection checked out for the duration of the
        # iteration; with a pool size >= 2, readers/writers still flow.
        async with (
            self._acquire() as db,
            db.execute("SELECT * FROM pastes") as cursor,
        ):
            while True:
                batch = await cursor.fetchmany(500)
                if not batch:
                    return
                for row in batch:
                    yield self._row_to_paste(row)

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(3600)
                async with self._acquire() as db:
                    await db.execute(
                        "DELETE FROM pastes WHERE expires_at IS NOT NULL AND expires_at < ?",
                        (int(time.time()),),
                    )
                    await db.commit()
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("SQLite cleanup pass failed; will retry next tick")

    async def ping(self) -> None:
        async with self._acquire() as db:
            await db.execute("SELECT 1")

    async def close(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._cleanup_task
        for conn in self._all_conns:
            with contextlib.suppress(Exception):
                await conn.close()
        self._all_conns.clear()
        self._pool = None
