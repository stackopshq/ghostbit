import hashlib
import json
import time
from typing import Optional

import redis.asyncio as aioredis

from .base import PasteData, StorageBackend


class RedisStorage(StorageBackend):
    def __init__(self, url: str) -> None:
        self.url = url
        self._client: Optional[aioredis.Redis] = None

    async def init(self) -> None:
        self._client = aioredis.from_url(self.url, decode_responses=True)

    def _key(self, paste_id: str) -> str:
        return f"paste:{paste_id}"

    async def save(self, paste: PasteData) -> None:
        data = json.dumps({
            "id": paste.id,
            "content": paste.content,
            "nonce": paste.nonce,
            "kdf_salt": paste.kdf_salt,
            "language": paste.language,
            "created_at": paste.created_at,
            "expires_at": paste.expires_at,
            "burn": paste.burn,
            "has_password": paste.has_password,
            "delete_token_hash": paste.delete_token_hash,
            "max_views": paste.max_views,
            "view_count": paste.view_count,
            "webhook_url": paste.webhook_url,
        })
        key = self._key(paste.id)
        if paste.expires_at:
            ttl = paste.expires_at - int(time.time())
            if ttl > 0:
                await self._client.setex(key, ttl, data)
        else:
            await self._client.set(key, data)

    async def get(self, paste_id: str) -> Optional[PasteData]:
        data = await self._client.get(self._key(paste_id))
        if data is None:
            return None
        d = json.loads(data)
        d.setdefault("max_views", None)
        d.setdefault("view_count", 0)
        d.setdefault("webhook_url", None)
        return PasteData(**d)

    async def increment_views(self, paste_id: str) -> int:
        key = self._key(paste_id)
        data = await self._client.get(key)
        if data is None:
            return 0
        d = json.loads(data)
        d["view_count"] = d.get("view_count", 0) + 1
        # Preserve TTL
        ttl = await self._client.ttl(key)
        new_data = json.dumps(d)
        if ttl > 0:
            await self._client.setex(key, ttl, new_data)
        else:
            await self._client.set(key, new_data)
        return d["view_count"]

    async def delete(self, paste_id: str, delete_token: str) -> bool:
        token_hash = hashlib.sha256(delete_token.encode()).hexdigest()
        key = self._key(paste_id)
        async with self._client.pipeline() as pipe:
            await pipe.get(key)
            await pipe.delete(key)
            results = await pipe.execute()
        raw = results[0]
        if raw is None:
            return False
        d = json.loads(raw)
        if d["delete_token_hash"] != token_hash:
            await self._client.set(key, raw)
            return False
        return True

    async def force_delete(self, paste_id: str) -> None:
        await self._client.delete(self._key(paste_id))

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
