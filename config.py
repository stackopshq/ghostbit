from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    storage_backend: str = "sqlite"           # "sqlite" or "redis"
    sqlite_path: str     = "/data/ghostbit.db"
    redis_url: str       = "redis://localhost:6379"
    max_paste_size: int  = 524288             # 512 KB
    port: int            = 8000

    # Optional shared secret for signing webhook payloads (HMAC-SHA256).
    # If set, every webhook delivery includes X-Ghostbit-Signature: sha256=<hex>.
    webhook_secret: str  = ""

    # ENCRYPTION_KEY is no longer used — all encryption is performed client-side (E2E).
    # Kept here so existing .env files don't cause startup errors.
    encryption_key: str  = ""

    model_config = {"env_file": ".env"}


settings = Settings()
