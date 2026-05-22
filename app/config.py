from pydantic import field_validator
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

    # Public-facing base URL (scheme + host [+ :port]), e.g. "https://paste.example.com".
    # Builds the absolute URLs in social-preview meta tags (og:image, og:url).
    # Empty → derived from the incoming request, which is correct for direct
    # exposure and for proxies that forward scheme + Host. Set it explicitly when
    # a TLS-terminating proxy would otherwise leave the app advertising http://.
    base_url: str = ""

    # Ignore extra env vars (e.g. a stale ENCRYPTION_KEY from pre-E2E setups)
    # instead of failing at startup.
    model_config = {"env_file": ".env", "extra": "ignore"}

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, v: str) -> str:
        # Fail fast on a malformed value rather than silently emitting broken
        # <meta> URLs. Trailing slash stripped so callers can join cleanly.
        v = v.strip().rstrip("/")
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("BASE_URL must start with http:// or https://")
        return v


settings = Settings()
