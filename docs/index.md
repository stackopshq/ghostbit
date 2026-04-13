# Ghostbit

**Self-hosted, end-to-end encrypted paste service.**


All content is encrypted in your browser before being sent to the server. The server stores ciphertext only — it can never read your pastes.

## Quickstart

```bash
git clone https://github.com/stackopshq/ghostbit
cd ghostbit
cp .env.example .env
docker compose up -d
# Open http://localhost:8000
```

No server-side key needed — all encryption happens in the browser.

## Install the CLI

```bash
pip install ghostbit-cli
```

```bash
cat file.py | gbit
gbit secrets.env --burn --expires 3600
echo "hello" | gbit -p
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
| **CLI** | `gbit` command — pipe anything, works with scripts |
| **REST API** | Full API for automation and integrations |
| **SQLite / Redis** | Two storage backends, swap with an env var |
