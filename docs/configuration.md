# Configuration

All configuration is done via environment variables (or a `.env` file at the project root).

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_BACKEND` | `sqlite` | `sqlite` or `redis` |
| `SQLITE_PATH` | `./ghostbit.db` | Path to the SQLite database file (Docker overrides to `/data/ghostbit.db`) |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `REDIS_PASSWORD` | — | Redis password. Injected into `REDIS_URL` automatically. Ignored if the URL already contains credentials. |
| `MAX_PASTE_SIZE` | `524288` | Maximum paste size in bytes (default: 512 KB) |
| `PORT` | `8000` | HTTP port the server listens on |
| `WEBHOOK_SECRET` | — | If set, signs webhook deliveries with HMAC-SHA256 (`X-Ghostbit-Signature`) |
| `RATE_LIMIT_CREATE` | `30/minute` | Rate limit for paste creation per IP (`POST /api/v1/pastes`) |
| `RATE_LIMIT_VIEW` | `120/minute` | Rate limit for paste reads per IP (`GET /api/v1/pastes/{id}`) |

!!! info "No server-side encryption key"
    All encryption is performed client-side (AES-256-GCM in the browser or CLI). The server never sees plaintext — no `ENCRYPTION_KEY` is needed.

## Storage backends

=== "SQLite"

    Default backend, no extra dependencies. An hourly cleanup task removes expired pastes.

    ```env
    STORAGE_BACKEND=sqlite
    SQLITE_PATH=/data/ghostbit.db
    ```

=== "Redis"

    Better for high-traffic instances. TTL is handled natively by Redis `EXPIRE`.

    ```env
    STORAGE_BACKEND=redis
    REDIS_URL=redis://localhost:6379
    ```

    Start with the Redis profile:

    ```bash
    STORAGE_BACKEND=redis docker compose --profile redis up -d
    ```

    **With a password** — two equivalent approaches:

    ```bash
    # Recommended: separate variable (password injected into URL automatically)
    STORAGE_BACKEND=redis REDIS_PASSWORD=mysecret docker compose --profile redis up -d
    ```

    ```env
    # Alternative: embed credentials directly in the URL
    REDIS_URL=redis://:mysecret@localhost:6379
    ```

    When `REDIS_PASSWORD` is set, the managed Redis container is started with `--requirepass` automatically.

## Rate limiting

Rate limits are applied per client IP using [slowapi](https://github.com/laurentS/slowapi).  
The format is `"N/period"` where period is `second`, `minute`, or `hour`.

```env
# Tighten limits on a public instance
RATE_LIMIT_CREATE=10/minute
RATE_LIMIT_VIEW=60/minute

# Loosen for internal / self-use instances
RATE_LIMIT_CREATE=200/minute
RATE_LIMIT_VIEW=600/minute
```

When a limit is exceeded the API returns `429 Too Many Requests`.

## .env example

```env
STORAGE_BACKEND=sqlite
SQLITE_PATH=/data/ghostbit.db
MAX_PASTE_SIZE=524288
PORT=8000

# Rate limiting (defaults shown)
# RATE_LIMIT_CREATE=30/minute
# RATE_LIMIT_VIEW=120/minute

# Optional: sign webhook deliveries
# WEBHOOK_SECRET=your_hex_encoded_secret_here
```
