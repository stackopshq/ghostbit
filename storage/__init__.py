from config import settings

from .base import StorageBackend


async def get_storage() -> StorageBackend:
    if settings.storage_backend == "redis":
        from .redis_backend import RedisStorage

        backend: StorageBackend = RedisStorage(settings.redis_url)
    else:
        from .sqlite import SQLiteStorage

        backend = SQLiteStorage(settings.sqlite_path)

    await backend.init()
    return backend
