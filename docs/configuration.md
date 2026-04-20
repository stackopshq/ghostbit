# Configuration

All configuration is done via environment variables (or a `.env` file at the project root).

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_BACKEND` | `sqlite` | `sqlite` or `redis` |
| `SQLITE_PATH` | `./ghostbit.db` | Path to the SQLite database file (Docker overrides to `/data/ghostbit.db`) |
| `SQLITE_POOL_SIZE` | `5` | Number of pooled SQLite connections. WAL enables parallel readers; raise if `ghostbit_sqlite_pool_wait_seconds` shows contention. |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `REDIS_PASSWORD` | — | Redis password. Injected into `REDIS_URL` automatically. Ignored if the URL already contains credentials. |
| `MAX_PASTE_SIZE` | `524288` | Maximum paste size in bytes (default: 512 KB) |
| `PORT` | `8000` | HTTP port the server listens on |
| `WEBHOOK_SECRET` | — | If set, signs webhook deliveries with HMAC-SHA256 (`X-Ghostbit-Signature`) |
| `RATE_LIMIT_CREATE` | `30/minute` | Rate limit for paste creation per IP (`POST /api/v1/pastes`) |
| `RATE_LIMIT_VIEW` | `120/minute` | Rate limit for paste reads per IP (`GET /api/v1/pastes/{id}`) |
| `TRUST_PROXY_HEADERS` | `false` | Read client IP from `X-Forwarded-For` for rate-limiting. See the [Reverse proxy](#reverse-proxy) note below before enabling. |

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

## Reverse proxy

When Ghostbit sits behind a reverse proxy (Nginx, Caddy, Traefik, Cloudflare…),
the direct peer address is the proxy's, not the client's — so per-IP rate limits
would apply globally. Enable `TRUST_PROXY_HEADERS=true` to key limits on
`X-Forwarded-For` instead.

The **rightmost** XFF entry is used: that's the IP appended by the hop nearest
to Ghostbit, which is the only entry you can trust. Leftmost entries are
client-controlled (a malicious client could forge `X-Forwarded-For: 1.2.3.4` to
impersonate another IP).

When `TRUST_PROXY_HEADERS=true`, the Docker image also starts uvicorn with
`--proxy-headers` so the real client IP is substituted for the proxy's address
in the access log and in `request.client.host`. Otherwise the uvicorn logs
would show only the reverse proxy's internal IP, which is not useful for
incident triage. If you run the server outside of Docker, pass those flags
yourself (`uvicorn app.main:app --proxy-headers --forwarded-allow-ips="*"`).

!!! warning "Multi-hop setups (CDN → LB → app)"
    If more than one trusted proxy sits between the client and Ghostbit, the
    rightmost entry will be the nearest proxy (not the client), and rate
    limits will apply to that proxy globally. Collapse the chain at the
    nearest proxy (Nginx: `set_real_ip_from <CDN-range>; real_ip_header
    X-Forwarded-For;`) so only one hop contributes by the time Ghostbit
    reads the header.

## Observability

Ghostbit exposes two unauthenticated endpoints for operators:

| Endpoint | Format | Purpose |
|----------|--------|---------|
| `/healthz` | JSON (`{"status": "ok"}`) | Liveness probe. Returns 503 if the storage backend is unreachable. |
| `/metrics` | Prometheus text | Scrape target for Prometheus/Grafana/Alertmanager. |

The `/metrics` endpoint has no sensitive data (only aggregate counters and a
latency histogram) but you can still restrict it to your scraper's IP at the
reverse proxy if you prefer.

Exposed metrics:

| Metric | Type | Labels |
|--------|------|--------|
| `ghostbit_pastes_created_total` | counter | `has_password` |
| `ghostbit_pastes_viewed_total` | counter | `burned` |
| `ghostbit_pastes_deleted_total` | counter | — |
| `ghostbit_webhook_deliveries_total` | counter | `outcome` (`ok` \| `timeout` \| `error` \| `ssrf_blocked`) |
| `ghostbit_http_request_duration_seconds` | histogram | `method`, `path`, `status` |
| `ghostbit_sqlite_pool_wait_seconds` | histogram | — |

`/healthz` and `/metrics` are excluded from the HTTP latency histogram so probe
traffic doesn't skew P99.

## .env example

```env
STORAGE_BACKEND=sqlite
SQLITE_PATH=/data/ghostbit.db
MAX_PASTE_SIZE=524288
PORT=8000

# SQLite pool (bump if ghostbit_sqlite_pool_wait_seconds shows contention)
# SQLITE_POOL_SIZE=5

# Rate limiting (defaults shown)
# RATE_LIMIT_CREATE=30/minute
# RATE_LIMIT_VIEW=120/minute

# Enable when behind a reverse proxy — rightmost X-Forwarded-For entry
# is used as the rate-limit key. See the Reverse proxy section above.
# TRUST_PROXY_HEADERS=true

# Optional: sign webhook deliveries
# WEBHOOK_SECRET=your_hex_encoded_secret_here
```
