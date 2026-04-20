from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    storage_backend: str = "sqlite"  # "sqlite" or "redis"
    sqlite_path: str = "./ghostbit.db"
    # Number of SQLite connections held in the pool. WAL mode lets multiple
    # readers progress in parallel; writers still serialize at the DB level.
    # Raise if `ghostbit_sqlite_pool_wait_seconds` histogram shows backlog.
    sqlite_pool_size: int = 5
    redis_url: str = "redis://localhost:6379"
    redis_password: str = ""  # injected into redis_url if set
    max_paste_size: int = 524288  # 512 KB
    port: int = 8000

    # Rate limits (slowapi / limits syntax: "N/period", e.g. "30/minute")
    rate_limit_create: str = "30/minute"  # POST /api/v1/pastes
    rate_limit_view: str = "120/minute"  # GET  /api/v1/pastes/{id}

    # Optional shared secret for signing webhook payloads (HMAC-SHA256).
    # If set, every webhook delivery includes X-Ghostbit-Signature: sha256=<hex>.
    webhook_secret: str = ""

    # Trust X-Forwarded-For for rate limiting. Enable ONLY when behind a
    # reverse proxy that strips/overwrites this header — otherwise clients
    # can spoof it and bypass rate limits.
    trust_proxy_headers: bool = False

    # Ignore extra env vars (e.g. a stale ENCRYPTION_KEY from pre-E2E setups)
    # instead of failing at startup.
    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
