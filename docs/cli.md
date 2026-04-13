# CLI

## Install

```bash
pip install ghostbit-cli
```

This installs the `gb` and `ghostbit` commands.

With optional extras for terminal rendering:

```bash
pip install "ghostbit-cli[all]"       # pygments + rich (recommended)
pip install "ghostbit-cli[color]"     # pygments — syntax highlighting
pip install "ghostbit-cli[markdown]"  # rich — Markdown rendering
```

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

## View a paste

Download, decrypt, and display a paste directly in the terminal:

```bash
# Non-password paste (key is in the URL fragment)
gb view https://paste.example.com/abc123#KEY~TOKEN

# Password-protected paste (prompts for password interactively)
gb view https://paste.example.com/abc123#~TOKEN

# Pipe to another tool
gb view https://paste.example.com/abc123#KEY~TOKEN | less
```

- Markdown pastes are rendered with titles, bold, lists, and code blocks (requires `rich`)
- Other languages are syntax-highlighted (requires `pygments`)
- Falls back to plain text if neither is installed
- Burn-after-read pastes display a warning on stderr after decryption

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

## Shell completion

Enable tab-completion for `gb` in your shell.

### Bash

```bash
# Activate for the current session
eval "$(gb completion bash)"

# Make it permanent
echo 'eval "$(gb completion bash)"' >> ~/.bashrc
```

### Zsh

```zsh
# Activate for the current session
eval "$(gb completion zsh)"

# Make it permanent
echo 'eval "$(gb completion zsh)"' >> ~/.zshrc
```

### Fish

```fish
# Activate for the current session
gb completion fish | source

# Make it permanent
gb completion fish > ~/.config/fish/completions/gb.fish
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
