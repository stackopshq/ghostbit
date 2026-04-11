# CLI

## Install

```bash
pip install ghostbit-cli
```

This installs the `gb` command.

---

## Configuration

```bash
# Set your self-hosted server
gb config set server https://paste.example.com

# Show current config
gb config show

# Remove a key
gb config unset server
```

Config is stored at `~/.config/ghostbit.toml`.

---

## Create a paste

### From stdin

```bash
cat main.py | gb
echo "hello world" | gb
git diff HEAD~1 | gb
```

### From a file

```bash
gb main.py
gb secrets.env
```

Language is auto-detected from the file extension.

---

## Options

| Flag | Short | Description |
|------|-------|-------------|
| `--lang LANG` | `-l` | Language hint (`python`, `go`, `rust`, `sql`, …) |
| `--expires SECONDS` | `-e` | TTL in seconds. `3600` = 1h, `86400` = 1d |
| `--burn` | `-b` | Delete after the first view |
| `--max-views N` | `-m` | Delete after N views |
| `--password PASS` | `-p` | Encrypt with a password (PBKDF2, client-side) |
| `--server URL` | `-s` | Override server URL for this invocation only |
| `--quiet` | `-q` | Print URL only (useful in scripts) |
| `--json` | | Print full JSON response including `full_url` |

---

## Examples

```bash
# Burn after read
cat deploy.sh | gb --burn

# Expire in 1 hour, max 3 views
gb config.yml --expires 3600 --max-views 3

# Password protected
echo "db_password=s3cr3t" | gb --password mysecret

# Language override
curl api.example.com/data | gb --lang json

# Scripting: URL only
URL=$(cat file.py | gb --quiet)
echo "Paste created: $URL"

# Full JSON response
cat data.json | gb --json
```

---

## Supported language extensions

Auto-detected from file extension when using `gb <file>`:

| Extension | Language |
|-----------|----------|
| `.py` | python |
| `.js` | javascript |
| `.ts` | typescript |
| `.go` | go |
| `.rs` | rust |
| `.rb` | ruby |
| `.sh`, `.bash`, `.zsh` | bash |
| `.html` | html |
| `.css` | css |
| `.sql` | sql |
| `.json` | json |
| `.yaml`, `.yml` | yaml |
| `.toml` | toml |
| `.md` | markdown |
| `.diff`, `.patch` | diff |
| `.java` | java |
| `.c` | c |
| `.cpp` | cpp |
| `.php` | php |
