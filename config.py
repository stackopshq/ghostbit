from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    storage_backend: str = "sqlite"           # "sqlite" or "redis"
    sqlite_path: str     = "/data/ghostbit.db"
    redis_url: str       = "redis://localhost:6379"
    redis_password: str  = ""                        # injected into redis_url if set
    max_paste_size: int  = 524288             # 512 KB
    port: int            = 8000

    # Rate limits (slowapi / limits syntax: "N/period", e.g. "30/minute")
    rate_limit_create: str = "30/minute"     # POST /api/v1/pastes
    rate_limit_view: str   = "120/minute"    # GET  /api/v1/pastes/{id}

    # Optional shared secret for signing webhook payloads (HMAC-SHA256).
    # If set, every webhook delivery includes X-Ghostbit-Signature: sha256=<hex>.
    webhook_secret: str  = ""

    # ENCRYPTION_KEY is no longer used — all encryption is performed client-side (E2E).
    # Kept here so existing .env files don't cause startup errors.
    encryption_key: str  = ""

    model_config = {"env_file": ".env"}


settings = Settings()
