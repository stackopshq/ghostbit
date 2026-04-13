import hashlib
import json
import time
from typing import Optional

import redis.asyncio as aioredis

from .base import PasteData, StorageBackend

# Atomically increments view_count inside the JSON blob and preserves TTL.
_LUA_INCREMENT_VIEWS = """
local data = redis.call('GET', KEYS[1])
if not data then return 0 end
local d = cjson.decode(data)
d['view_count'] = (d['view_count'] or 0) + 1
local new_data = cjson.encode(d)
local ttl = redis.call('TTL', KEYS[1])
if ttl > 0 then
    redis.call('SETEX', KEYS[1], ttl, new_data)
else
    redis.call('SET', KEYS[1], new_data)
end
return d['view_count']
"""

# Atomically checks the delete token and deletes the key in one round-trip.
_LUA_DELETE = """
local data = redis.call('GET', KEYS[1])
if not data then return 0 end
local d = cjson.decode(data)
if d['delete_token_hash'] ~= ARGV[1] then return 0 end
redis.call('DEL', KEYS[1])
return 1
"""


class RedisStorage(StorageBackend):
    def __init__(self, url: str) -> None:
        self.url = url
        self._client: Optional[aioredis.Redis] = None

    async def init(self) -> None:
        self._client = aioredis.from_url(self.url, decode_responses=True)
        self._increment_views_script = self._client.register_script(_LUA_INCREMENT_VIEWS)
        self._delete_script = self._client.register_script(_LUA_DELETE)

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
            if ttl <= 0:
                return  # Already expired, don't store
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
        result = await self._increment_views_script(keys=[self._key(paste_id)])
        return int(result)

    async def delete(self, paste_id: str, delete_token: str) -> bool:
        token_hash = hashlib.sha256(delete_token.encode()).hexdigest()
        result = await self._delete_script(keys=[self._key(paste_id)], args=[token_hash])
        return bool(result)

    async def force_delete(self, paste_id: str) -> None:
        await self._client.delete(self._key(paste_id))

    async def ping(self) -> None:
        await self._client.ping()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
