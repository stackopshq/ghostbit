import asyncio
import hashlib
import time
from typing import Optional

import aiosqlite

from .base import PasteData, StorageBackend

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

_MIGRATE = """
ALTER TABLE pastes ADD COLUMN max_views INTEGER;
"""
_MIGRATE2 = """
ALTER TABLE pastes ADD COLUMN view_count INTEGER NOT NULL DEFAULT 0;
"""
_MIGRATE3 = """
ALTER TABLE pastes ADD COLUMN webhook_url TEXT;
"""


class SQLiteStorage(StorageBackend):
    def __init__(self, path: str) -> None:
        self.path = path
        self._cleanup_task: Optional[asyncio.Task] = None

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(_CREATE_TABLE)
            # Migrate existing DBs that lack the new columns
            for stmt in (_MIGRATE, _MIGRATE2, _MIGRATE3):
                try:
                    await db.execute(stmt)
                except Exception:
                    pass
            await db.commit()
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def save(self, paste: PasteData) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO pastes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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

    async def get(self, paste_id: str) -> Optional[PasteData]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM pastes WHERE id = ?", (paste_id,)
            ) as cursor:
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

    async def increment_views(self, paste_id: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE pastes SET view_count = view_count + 1 WHERE id = ?",
                (paste_id,),
            )
            await db.commit()
            async with db.execute(
                "SELECT view_count FROM pastes WHERE id = ?", (paste_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else 0

    async def delete(self, paste_id: str, delete_token: str) -> bool:
        token_hash = hashlib.sha256(delete_token.encode()).hexdigest()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "DELETE FROM pastes WHERE id = ? AND delete_token_hash = ?",
                (paste_id, token_hash),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def force_delete(self, paste_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM pastes WHERE id = ?", (paste_id,))
            await db.commit()

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(3600)
            async with aiosqlite.connect(self.path) as db:
                await db.execute(
                    "DELETE FROM pastes WHERE expires_at IS NOT NULL AND expires_at < ?",
                    (int(time.time()),),
                )
                await db.commit()

    async def close(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
