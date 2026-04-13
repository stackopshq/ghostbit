# CLI

## Install

```bash
pip install ghostbit-cli
```

This installs the `gbit` and `ghostbit` commands.

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
gbit config set server https://paste.example.com

# Show current config
gbit config show

# Remove a key
gbit config unset server
```

Config is stored at `~/.config/ghostbit.toml`.

---

## Create a paste

### From stdin

```bash
cat main.py | gbit
echo "hello world" | gbit
git diff HEAD~1 | gbit
```

### From a file

```bash
gbit main.py
gbit secrets.env
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
| `--password [PASS]` | `-p` | Encrypt with a password. Omit value to be prompted securely. |
| `--server URL` | `-s` | Override server URL for this invocation only |
| `--quiet` | `-q` | Print URL only (useful in scripts) |
| `--json` | | Print full JSON response including `full_url` |
| `--no-history` | | Don't save this paste to local history |
| `--version` | `-V` | Print version and exit |

---

## Delete a paste

```bash
gbit delete https://paste.example.com/abc123#KEY~TOKEN
```

The delete token is read from the URL fragment (after `~`). No server-side secret needed — the token was generated at creation time and embedded in the URL.

---

## Paste history

All created pastes are saved locally to `~/.local/share/ghostbit/history.jsonl`.  
Nothing is sent to the server — this file stays on your machine only.

```bash
# List recent pastes
gbit list

# Wipe local history
gbit list --clear
```

Example output:

```
ID           Lang            Created      Expires     URL
abc123       python          2h ago       in 22h      https://paste.example.com/abc123#KEY~TOKEN
def456       json            5d ago       never       https://paste.example.com/def456#KEY~TOKEN
```

---

## View a paste

Download, decrypt, and display a paste directly in the terminal:

```bash
# Non-password paste (key is in the URL fragment)
gbit view https://paste.example.com/abc123#KEY~TOKEN

# Password-protected paste (prompts for password interactively)
gbit view https://paste.example.com/abc123#~TOKEN

# Pipe to another tool
gbit view https://paste.example.com/abc123#KEY~TOKEN | less
```

- Markdown pastes are rendered with titles, bold, lists, and code blocks (requires `rich`)
- Other languages are syntax-highlighted (requires `pygments`)
- Falls back to plain text if neither is installed
- Burn-after-read pastes display a warning on stderr after decryption

---

## Examples

```bash
# Burn after read
cat deploy.sh | gbit --burn

# Expire in 1 hour, max 3 views
gbit config.yml --expires 3600 --max-views 3

# Password protected (secure prompt)
echo "db_password=s3cr3t" | gbit -p

# Password inline (visible in process list)
gbit file.py --password mysecret

# Language override
curl api.example.com/data | gbit --lang json

# Scripting: URL only
URL=$(cat file.py | gbit --quiet)
echo "Paste created: $URL"

# Skip local history for sensitive pastes
cat secrets.env | gbit --burn --no-history

# Full JSON response
cat data.json | gbit --json
```

---

## Shell completion

Enable tab-completion for `gbit` in your shell.

### Bash

```bash
# Activate for the current session
eval "$(gbit completion bash)"

# Make it permanent
echo 'eval "$(gbit completion bash)"' >> ~/.bashrc
```

### Zsh

```zsh
# Activate for the current session
eval "$(gbit completion zsh)"

# Make it permanent
echo 'eval "$(gbit completion zsh)"' >> ~/.zshrc
```

### Fish

```fish
# Activate for the current session
gbit completion fish | source

# Make it permanent
gbit completion fish > ~/.config/fish/completions/gbit.fish
```

---

## Supported language extensions

Auto-detected from file extension or filename when using `gbit <file>`:

| Extension / Name | Language |
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
| `.cs` | csharp |
| `.php` | php |
| `.kt` | kotlin |
| `.swift` | swift |
| `.lua` | lua |
| `.r` | r |
| `Dockerfile` | dockerfile |
| `Makefile` | makefile |
