import asyncio
import contextlib
import hashlib
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite

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


class SQLiteStorage(StorageBackend):
    def __init__(self, path: str) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None
        # Serializes multi-statement transactions on the shared connection so
        # concurrent requests can't interleave statements inside a BEGIN…COMMIT.
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    async def init(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        # WAL gives concurrent reads with a single writer and survives this
        # pragma because it persists at the DB file level. synchronous=NORMAL
        # is the standard durability/perf tradeoff for WAL.
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.execute(_CREATE_TABLE)
        existing = await self._column_names("pastes")
        for col, ddl in _EXPECTED_COLUMNS.items():
            if col not in existing:
                await self._db.execute(f"ALTER TABLE pastes ADD COLUMN {col} {ddl}")
        await self._db.commit()
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _column_names(self, table: str) -> set[str]:
        async with self._db.execute(f"PRAGMA table_info({table})") as cursor:
            rows = await cursor.fetchall()
        return {row[1] for row in rows}

    async def save(self, paste: PasteData) -> bool:
        async with self._lock:
            cursor = await self._db.execute(
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
            await self._db.commit()
            return cursor.rowcount > 0

    async def get(self, paste_id: str) -> PasteData | None:
        async with self._db.execute("SELECT * FROM pastes WHERE id = ?", (paste_id,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
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

    async def increment_and_check_burn(self, paste_id: str) -> tuple[int | None, bool]:
        async with self._lock:
            await self._db.execute("BEGIN IMMEDIATE")
            async with self._db.execute(
                "UPDATE pastes SET view_count = view_count + 1 "
                "WHERE id = ? "
                "RETURNING view_count, burn, max_views",
                (paste_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if row is None:
                await self._db.commit()
                return None, False
            view_count, burn, max_views = row["view_count"], row["burn"], row["max_views"]
            should_burn = bool(burn) or (max_views is not None and view_count >= max_views)
            if should_burn:
                await self._db.execute("DELETE FROM pastes WHERE id = ?", (paste_id,))
            await self._db.commit()
            return view_count, should_burn

    async def delete(self, paste_id: str, delete_token: str) -> bool:
        token_hash = hashlib.sha256(delete_token.encode()).hexdigest()
        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM pastes WHERE id = ? AND delete_token_hash = ?",
                (paste_id, token_hash),
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def force_delete(self, paste_id: str) -> None:
        async with self._lock:
            await self._db.execute("DELETE FROM pastes WHERE id = ?", (paste_id,))
            await self._db.commit()

    async def iter_all(self) -> AsyncIterator[PasteData]:
        # Fetch IDs up-front so the admin cursor can't starve concurrent
        # writes on the shared connection (aiosqlite serializes operations).
        async with self._db.execute("SELECT id FROM pastes") as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            paste = await self.get(row["id"])
            if paste is not None:
                yield paste

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(3600)
                async with self._lock:
                    await self._db.execute(
                        "DELETE FROM pastes WHERE expires_at IS NOT NULL AND expires_at < ?",
                        (int(time.time()),),
                    )
                    await self._db.commit()
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("SQLite cleanup pass failed; will retry next tick")

    async def ping(self) -> None:
        await self._db.execute("SELECT 1")

    async def close(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._cleanup_task
        if self._db is not None:
            await self._db.close()
            self._db = None
