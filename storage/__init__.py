from urllib.parse import urlparse, urlunparse

from config import settings

from .base import StorageBackend


def _redis_url() -> str:
    url = settings.redis_url
    if not settings.redis_password:
        return url
    parsed = urlparse(url)
    # Only inject if no password already present in the URL
    if not parsed.password:
        netloc = f":{settings.redis_password}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        parsed = parsed._replace(netloc=netloc)
    return urlunparse(parsed)


async def get_storage() -> StorageBackend:
    if settings.storage_backend == "redis":
        from .redis_backend import RedisStorage

        backend: StorageBackend = RedisStorage(_redis_url())
    else:
        from .sqlite import SQLiteStorage

        backend = SQLiteStorage(settings.sqlite_path)

    await backend.init()
    return backend
