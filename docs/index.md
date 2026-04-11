# Ghostbit

**Self-hosted, end-to-end encrypted paste service.**


All content is encrypted in your browser before being sent to the server. The server stores ciphertext only — it can never read your pastes.

## Quickstart

```bash
# 1. Generate an encryption key
python3 -c "import secrets; print(secrets.token_hex(32))"

# 2. Configure and start
cp .env.example .env   # fill in ENCRYPTION_KEY
docker compose up -d

# 3. Open http://localhost:8000
```

## Install the CLI

```bash
pip install ghostbit-cli
```

```bash
cat file.py | gb
gb secrets.env --burn --expires 3600
echo "hello" | gb --password mysecret
```

## Features

| Feature | Description |
|---------|-------------|
| **True E2E encryption** | AES-256-GCM, key lives in URL fragment — never sent to server |
| **Password protection** | PBKDF2-SHA256 (600k iterations) key derivation, client-side |
| **Burn after read** | Deleted permanently after the first view |
| **Max views** | Automatically deleted after N reads |
| **Expiration** | TTL from 5 minutes to 1 year |
| **Webhook** | POST notification each time a paste is viewed |
| **Language detection** | Auto-detected from content or file extension |
| **Markdown preview** | Rendered in-browser for markdown pastes |
| **CLI** | `gb` command — pipe anything, works with scripts |
| **REST API** | Full API for automation and integrations |
| **SQLite / Redis** | Two storage backends, swap with an env var |
