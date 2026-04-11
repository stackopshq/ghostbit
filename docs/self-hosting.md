# Self-hosting

## Docker images

| Registry | Image |
|----------|-------|
| Docker Hub | [`stackopshq/ghostbit`](https://hub.docker.com/r/stackopshq/ghostbit) |
| GHCR | `ghcr.io/stackopshq/ghostbit` |

Available tags: `latest`, `edge`, semver (`1.0.0`, `1.0`, `1`).

---

## Docker Compose (recommended)

### SQLite

```bash
git clone https://github.com/stackopshq/ghostbit
cd ghostbit
cp .env.example .env
# Edit .env: set ENCRYPTION_KEY
docker compose up -d
```

### Redis

```bash
STORAGE_BACKEND=redis docker compose --profile redis up -d
```

Redis data is persisted via AOF + RDB snapshots on a named Docker volume.

---

## Nginx reverse proxy

```nginx
server {
    listen 443 ssl;
    server_name paste.example.com;

    ssl_certificate     /etc/letsencrypt/live/paste.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/paste.example.com/privkey.pem;

    client_max_body_size 10M;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}

# Redirect HTTP → HTTPS
server {
    listen 80;
    server_name paste.example.com;
    return 301 https://$host$request_uri;
}
```

!!! tip "HTTPS is required in production"
    `crypto.subtle` (Web Crypto API) requires a Secure Context.
    Without HTTPS, the browser will refuse to encrypt pastes.

---

## Caddy reverse proxy

```caddy
paste.example.com {
    reverse_proxy localhost:8000
}
```

Caddy handles HTTPS automatically via Let's Encrypt.

---

## Data persistence

| Backend | Persistence |
|---------|-------------|
| SQLite | Named Docker volume `ghostbit_data` mounted at `/data` |
| Redis | Named Docker volume `redis_data`, AOF + RDB snapshots |

### Backup SQLite

```bash
docker compose exec ghostbit sqlite3 /data/ghostbit.db ".backup /data/ghostbit.db.bak"
docker compose cp ghostbit:/data/ghostbit.db.bak ./backup.db
```

### Backup Redis

```bash
docker compose exec redis redis-cli BGSAVE
docker compose cp redis:/data/dump.rdb ./dump.rdb
```

---

## Updating

```bash
git pull
docker compose up -d --build
```

---

## Privacy

- No IP addresses or User-Agent strings are ever logged
- Paste IDs are `secrets.token_urlsafe(6)` — random, non-sequential
- Burn-after-read fires only on API reads, not on HTML page loads
- The server never sees plaintext or passwords
