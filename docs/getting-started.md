# Getting started

## Requirements

- Docker + Docker Compose — recommended
- Or Python 3.10+ for a manual install

---

## Docker (recommended)

Images are available on Docker Hub and GHCR:

```bash
docker pull stackopshq/ghostbit          # Docker Hub
docker pull ghcr.io/stackopshq/ghostbit  # GitHub Container Registry
```

```bash
git clone https://github.com/stackopshq/ghostbit
cd ghostbit
cp .env.example .env
```

No server-side encryption key needed — all encryption happens in the client.

```bash
# Start with SQLite (default)
docker compose up -d

# Start with Redis
STORAGE_BACKEND=redis docker compose --profile redis up -d
```

The server is available at `http://localhost:8000`.

---

## Manual install

```bash
git clone https://github.com/stackopshq/ghostbit
cd ghostbit
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0
```

!!! warning "Use `--host 0.0.0.0`"
    The Web Crypto API (`crypto.subtle`) requires a **Secure Context**.
    Browsers grant it to `localhost` but not `127.0.0.1`.
    The `--host 0.0.0.0` flag ensures you can reach the app via `localhost`.

---

## Install the CLI

```bash
pip install ghostbit-cli
```

Configure it to point to your instance:

```bash
gbit config set server https://paste.example.com
gbit config show
```

Then paste anything:

```bash
cat main.py | gbit
```
