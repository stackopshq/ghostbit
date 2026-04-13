# PowerShell CLI

A native PowerShell module that mirrors the Python `gbit` CLI.  
All encryption is done client-side using the built-in .NET cryptography APIs — no external dependencies.

**Requirements:** PowerShell 7.0+ (Windows, macOS, or Linux)

---

## Install

### Option 1 — copy to your module path

```powershell
$dest = "$($env:PSModulePath.Split([IO.Path]::PathSeparator)[0])\Ghostbit"
New-Item -ItemType Directory -Path $dest -Force
Copy-Item cli/powershell/Ghostbit.* $dest
```

### Option 2 — import directly

```powershell
Import-Module /path/to/ghostbit/cli/powershell/Ghostbit.psm1
```

Add the import to your `$PROFILE` to make it permanent.

---

## Configuration

```powershell
# Set your self-hosted server
Invoke-GhostbitConfig set server https://paste.example.com

# Show current config
Invoke-GhostbitConfig show

# Remove a key
Invoke-GhostbitConfig unset server
```

Config is stored at:

| Platform | Path |
|----------|------|
| Windows  | `%APPDATA%\ghostbit\config.toml` |
| macOS / Linux | `~/.config/ghostbit.toml` |

---

## Create a paste

### From the pipeline

```powershell
Get-Content main.py | gbit
Get-Content main.py | New-GhostbitPaste
```

### From a file

```powershell
gbit main.py
New-GhostbitPaste main.py
```

Language is auto-detected from the file extension.

---

## Options

| Parameter | Short alias | Description |
|-----------|-------------|-------------|
| `-Language` | `-l` (n/a in PS) | Language hint (`python`, `go`, `rust`, `sql`, …) |
| `-ExpiresIn` | | TTL in seconds. `3600` = 1 h, `86400` = 1 d |
| `-Burn` | | Delete after the first view |
| `-MaxViews N` | | Delete after N views |
| `-Password` | | Encrypt with a password (PBKDF2-SHA256, client-side) |
| `-Server URL` | | Override server URL for this invocation only |
| `-Quiet` | | Print URL only (useful in scripts) |
| `-AsJson` | | Print full API response as JSON including `full_url` |

---

## View a paste

Download, decrypt, and print a paste directly in the terminal:

```powershell
# Non-password paste (key is in the URL fragment)
Get-GhostbitPaste "https://paste.example.com/abc123#KEY~TOKEN"
gbitv "https://paste.example.com/abc123#KEY~TOKEN"

# Password-protected paste (prompts interactively)
gbitv "https://paste.example.com/abc123#~TOKEN"

# Pipe to a pager
gbitv "https://paste.example.com/abc123#KEY~TOKEN" | more
```

---

## Delete a paste

```powershell
Remove-GhostbitPaste "https://paste.example.com/abc123#KEY~TOKEN"
gbitd "https://paste.example.com/abc123#KEY~TOKEN"
```

The delete token is read from the URL fragment (after `~`).

---

## Paste history

All created pastes are saved locally. Nothing is sent to the server.

| Platform | Path |
|----------|------|
| Windows | `%LOCALAPPDATA%\ghostbit\history.jsonl` |
| macOS / Linux | `~/.local/share/ghostbit/history.jsonl` |

```powershell
# List recent pastes
Get-GhostbitHistory
gbith

# Wipe local history
Get-GhostbitHistory -Clear
gbith -Clear
```

---

## Examples

```powershell
# Burn after read
Get-Content deploy.ps1 | gbit -Burn

# Expire in 1 hour, max 3 views
gbit config.yml -ExpiresIn 3600 -MaxViews 3

# Password protected
"db_password=s3cr3t" | gbit -Password mysecret

# Language override
Invoke-RestMethod https://api.example.com/data | ConvertTo-Json | gbit -Language json

# Scripting: URL only
$url = Get-Content file.py | gbit -Quiet
Write-Host "Paste created: $url"

# Full JSON response
Get-Content data.json | gbit -AsJson
```

---

## Supported language extensions

Auto-detected from file extension when using `gbit <file>`:

| Extension | Language |
|-----------|----------|
| `.py` | python |
| `.js` | javascript |
| `.ts` | typescript |
| `.go` | go |
| `.rs` | rust |
| `.ps1`, `.psm1`, `.psd1` | powershell |
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
