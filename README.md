<p align="center">
  <img src="static/logo.png" alt="Ghostbit" width="90">
</p>

<h1 align="center">Ghostbit</h1>

<p align="center">
  Self-hosted, end-to-end encrypted paste service.<br>
  The server stores ciphertext only — it can <strong>never</strong> read your content.
</p>

<p align="center">
  A modern, privacy-first alternative to Pastebin and PrivateBin.
</p>

<p align="center">
  <a href="https://docs.ghostbit.dev">Documentation</a>
  &nbsp;·&nbsp;
  <a href="https://pypi.org/project/ghostbit-cli">CLI on PyPI</a>
  &nbsp;·&nbsp;
  <a href="#self-hosting">Self-hosting</a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10+-bc13fe?style=flat-square&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.100+-bc13fe?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-bc13fe?style=flat-square">
  <img alt="PyPI" src="https://img.shields.io/pypi/v/ghostbit-cli?style=flat-square&color=bc13fe&label=ghostbit-cli">
</p>

---

## How it works

Ghostbit encrypts your content **in the browser** using the Web Crypto API before sending anything to the server. The decryption key lives exclusively in the URL fragment — it is never transmitted over the network.

```
https://paste.example.com/aB3kZx9m#KEY~DELETE_TOKEN
                                    ↑
                          never sent to the server
```

| Paste type | Key source | Where the key lives |
|---|---|---|
| No password | `crypto.subtle.generateKey()` | URL `#fragment` |
| With password | PBKDF2-SHA256 (600k iter) | User's memory |

---

## Features

- **True E2E encryption** — AES-256-GCM, server sees ciphertext only
- **Burn after read** — deleted permanently after the first view
- **Max views** — auto-deleted after N reads
- **Expiration** — from 5 minutes to 1 year
- **Password protection** — client-side key derivation, password never leaves the browser
- **Webhook** — POST notification on each read
- **Language detection** — auto-detected from content or file extension
- **Markdown preview** — rendered in-browser
- **CLI** — `gb` command, pipe anything from your terminal
- **REST API** — full API for automation and integrations
- **SQLite / Redis** — swap storage backends with a single env var

---

## CLI

```bash
pip install ghostbit-cli
```

```bash
# Paste from stdin
cat main.py | gb

# Paste a file (language auto-detected)
gb secrets.env --burn --expires 3600

# Password-protected
echo "db_pass=s3cr3t" | gb --password mysecret

# Scripting
URL=$(cat deploy.sh | gb --quiet)

# Point to your instance
gb config set server https://paste.example.com
```

---

## Self-hosting

### Docker

```bash
docker pull stackopshq/ghostbit          # Docker Hub
docker pull ghcr.io/stackopshq/ghostbit  # GHCR
```

```bash
git clone https://github.com/stackopshq/ghostbit
cd ghostbit
cp .env.example .env
docker compose up -d
```

### With Redis

```bash
STORAGE_BACKEND=redis docker compose --profile redis up -d
```

### Podman Quadlet

Create `/etc/containers/systemd/ghostbit.container` (system-wide) or `~/.config/containers/systemd/ghostbit.container` (rootless):

```ini
[Unit]
Description=Ghostbit paste service
After=network-online.target

[Container]
Image=ghcr.io/stackopshq/ghostbit:latest
PublishPort=8000:8000
Volume=ghostbit_data:/data

Environment=STORAGE_BACKEND=sqlite
Environment=SQLITE_PATH=/data/ghostbit.db
Environment=MAX_PASTE_SIZE=524288
Environment=PORT=8000

[Service]
Restart=always

[Install]
WantedBy=default.target
```

```bash
# Reload systemd and start
systemctl --user daemon-reload
systemctl --user enable --now ghostbit
```

For Redis, add a `ghostbit-redis.container` alongside and use `After=ghostbit-redis.service` + `Environment=STORAGE_BACKEND=redis` + `Environment=REDIS_URL=redis://ghostbit-redis:6379`. Podman Quadlet handles the pod networking automatically.

---

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_BACKEND` | `sqlite` | `sqlite` or `redis` |
| `SQLITE_PATH` | `/data/ghostbit.db` | SQLite file path |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `MAX_PASTE_SIZE` | `524288` | Max paste size in bytes (512 KB) |
| `PORT` | `8000` | Server port |

---

## API

```bash
# Create (content must be pre-encrypted — use the CLI or e2e.js)
curl -X POST https://paste.example.com/api/v1/pastes \
  -H "Content-Type: application/json" \
  -d '{"content":"<base64 ciphertext>","nonce":"<base64 nonce>"}'

# Delete
curl -X DELETE https://paste.example.com/api/v1/pastes/{id} \
  -H "X-Delete-Token: <token>"
```

Full API reference at [docs.ghostbit.dev/api](https://docs.ghostbit.dev/api).

---

## License

MIT
