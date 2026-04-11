# Configuration

All configuration is done via environment variables (or a `.env` file at the project root).

## Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `ENCRYPTION_KEY` | — | **Yes** | Hex-encoded 32-byte server key. Used to hash delete tokens. |
| `STORAGE_BACKEND` | `sqlite` | No | `sqlite` or `redis` |
| `SQLITE_PATH` | `/data/ghostbit.db` | No | Path to the SQLite database file |
| `REDIS_URL` | `redis://localhost:6379` | No | Redis connection URL |
| `MAX_PASTE_SIZE` | `524288` | No | Maximum paste size in bytes (default: 512 KB) |
| `PORT` | `8000` | No | HTTP port the server listens on |
| `WEBHOOK_SECRET` | — | No | If set, signs webhook deliveries with HMAC-SHA256 (`X-Ghostbit-Signature`) |

## Generating an encryption key

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

The app refuses to start without `ENCRYPTION_KEY`.

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

## .env example

```env
ENCRYPTION_KEY=your_hex_encoded_32_byte_key_here
STORAGE_BACKEND=sqlite
SQLITE_PATH=/data/ghostbit.db
MAX_PASTE_SIZE=524288
PORT=8000

# Optional: sign webhook deliveries
# WEBHOOK_SECRET=your_hex_encoded_secret_here
```
