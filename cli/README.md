# Ghostbit CLI

Command-line tool for [Ghostbit](https://github.com/stackopshq/ghostbit) — a self-hosted, end-to-end encrypted paste service.

All content is encrypted **in the client** before being sent to the server. The server never sees your plaintext.

## Install

```bash
pip install ghostbit-cli
```

With syntax highlighting and Markdown rendering:

```bash
pip install "ghostbit-cli[all]"       # pygments + rich
pip install "ghostbit-cli[color]"     # pygments only (syntax highlighting)
pip install "ghostbit-cli[markdown]"  # rich only (Markdown rendering)
```

## Usage

```bash
# Paste from stdin
cat file.py | gbit

# Paste a file (language auto-detected from extension)
gbit file.py

# With options
gbit file.py --lang python --burn --expires 3600

# Password-protected paste (prompted securely)
echo "secret" | gbit -p

# Or pass inline (visible in process list)
gbit file.py --password mysecret

# View and decrypt a paste in the terminal
gbit view https://paste.example.com/abc123#KEY~TOKEN

# View a password-protected paste (prompts for password)
gbit view https://paste.example.com/abc123#~TOKEN

# Output JSON (includes full URL with decryption key)
cat data.json | gbit --json

# Point to your self-hosted instance
gbit config set server https://paste.example.com
```

## Options

| Flag | Short | Description |
|------|-------|-------------|
| `--lang` | `-l` | Language hint (python, go, rust, …) |
| `--expires` | `-e` | TTL in seconds (3600 = 1h, 86400 = 1d) |
| `--burn` | `-b` | Delete after the first view |
| `--max-views` | `-m` | Delete after N views |
| `--password` | `-p` | Encrypt with a password (prompted if no value given) |
| `--server` | `-s` | Override server URL for this call |
| `--quiet` | `-q` | Print URL only |
| `--json` | | Print full JSON response |
| `--no-history` | | Don't save to local history |
| `--version` | `-V` | Print version and exit |

## Configuration

```bash
gbit config set server https://paste.example.com
gbit config show
gbit config unset server
```

Config is stored at `~/.config/ghostbit.toml`.

## Security Note

The local history (`~/.local/share/ghostbit/history.jsonl`) stores full URLs **including decryption keys**. Use `--no-history` for sensitive pastes, or clear history with `gbit list --clear`.

## Self-hosting

See the [Ghostbit server repository](https://github.com/stackopshq/ghostbit) for Docker and manual setup instructions.

## License

MIT
