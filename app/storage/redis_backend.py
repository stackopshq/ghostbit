import hashlib
import json
import time
from collections.abc import AsyncIterator

import redis.asyncio as aioredis

from .base import PasteData, StorageBackend

# Atomically increment view_count, burn if needed, preserve TTL.
# Returns [view_count, burned] or [-1, 0] when the key does not exist.
_LUA_INCREMENT_AND_CHECK_BURN = """
local data = redis.call('GET', KEYS[1])
if not data then return {-1, 0} end
local d = cjson.decode(data)
d['view_count'] = (d['view_count'] or 0) + 1
local new_count = d['view_count']
local burn = d['burn'] == true
local mv = d['max_views']
local hit_max = (mv ~= nil and mv ~= cjson.null and new_count >= mv)
if burn or hit_max then
    redis.call('DEL', KEYS[1])
    return {new_count, 1}
end
local new_data = cjson.encode(d)
local ttl = redis.call('TTL', KEYS[1])
if ttl > 0 then
    redis.call('SETEX', KEYS[1], ttl, new_data)
else
    redis.call('SET', KEYS[1], new_data)
end
return {new_count, 0}
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
        self._client: aioredis.Redis | None = None

    async def init(self) -> None:
        self._client = aioredis.from_url(self.url, decode_responses=True)
        self._increment_and_check_burn_script = self._client.register_script(
            _LUA_INCREMENT_AND_CHECK_BURN
        )
        self._delete_script = self._client.register_script(_LUA_DELETE)

    def _key(self, paste_id: str) -> str:
        return f"paste:{paste_id}"

    async def save(self, paste: PasteData) -> bool:
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
                return True  # Already expired, caller gets no-op success
            result = await self._client.set(key, data, ex=ttl, nx=True)
        else:
            result = await self._client.set(key, data, nx=True)
        return bool(result)

    async def get(self, paste_id: str) -> PasteData | None:
        data = await self._client.get(self._key(paste_id))
        if data is None:
            return None
        d = json.loads(data)
        d.setdefault("max_views", None)
        d.setdefault("view_count", 0)
        d.setdefault("webhook_url", None)
        return PasteData(**d)

    async def increment_and_check_burn(
        self, paste_id: str
    ) -> tuple[int | None, bool]:
        result = await self._increment_and_check_burn_script(keys=[self._key(paste_id)])
        view_count, burned = int(result[0]), bool(result[1])
        if view_count < 0:
            return None, False
        return view_count, burned

    async def delete(self, paste_id: str, delete_token: str) -> bool:
        token_hash = hashlib.sha256(delete_token.encode()).hexdigest()
        result = await self._delete_script(keys=[self._key(paste_id)], args=[token_hash])
        return bool(result)

    async def force_delete(self, paste_id: str) -> None:
        await self._client.delete(self._key(paste_id))

    async def iter_all(self) -> AsyncIterator[PasteData]:
        # SCAN avoids KEYS' O(N) blocking scan on large DBs.
        async for key in self._client.scan_iter(match="paste:*", count=500):
            data = await self._client.get(key)
            if data is None:
                continue
            d = json.loads(data)
            d.setdefault("max_views", None)
            d.setdefault("view_count", 0)
            d.setdefault("webhook_url", None)
            yield PasteData(**d)

    async def ping(self) -> None:
        await self._client.ping()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
