# Ghostbit CLI

Command-line tool for [Ghostbit](https://github.com/stackopshq/ghostbit) — a self-hosted, end-to-end encrypted paste service.

All content is encrypted **in the client** before being sent to the server. The server never sees your plaintext.

## Install

```bash
pip install ghostbit-cli
```

## Usage

```bash
# Paste from stdin
cat file.py | gb

# Paste a file (language auto-detected from extension)
gb file.py

# With options
gb file.py --lang python --burn --expires 3600

# Password-protected paste
echo "secret" | gb --password mysecret

# Output JSON (includes full URL with decryption key)
cat data.json | gb --json

# Point to your self-hosted instance
gb config set server https://paste.example.com
```

## Options

| Flag | Short | Description |
|------|-------|-------------|
| `--lang` | `-l` | Language hint (python, go, rust, …) |
| `--expires` | `-e` | TTL in seconds (3600 = 1h, 86400 = 1d) |
| `--burn` | `-b` | Delete after the first view |
| `--max-views` | `-m` | Delete after N views |
| `--password` | `-p` | Encrypt with a password |
| `--server` | `-s` | Override server URL for this call |
| `--quiet` | `-q` | Print URL only |
| `--json` | | Print full JSON response |

## Configuration

```bash
gb config set server https://paste.example.com
gb config show
gb config unset server
```

Config is stored at `~/.config/ghostbit.toml`.

## Self-hosting

See the [Ghostbit server repository](https://github.com/stackopshq/ghostbit) for Docker and manual setup instructions.

## License

MIT
