#!/usr/bin/env python3
"""
Ghostbit CLI — create and view pastes from the terminal.

Usage:
  cat file.py | gbit
  gbit file.py
  gbit file.py --lang python --burn
  gbit view https://paste.example.com/abc123#KEY~TOKEN
  gbit config set server https://paste.example.com
  gbit config show
"""

import argparse
import base64
import getpass
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Version is read from the installed package metadata (single source of truth:
# cli/pyproject.toml). Falls back to "dev" when running from a source checkout.
try:
    from importlib.metadata import PackageNotFoundError, version as _pkg_version
    try:
        __version__ = _pkg_version("ghostbit-cli")
    except PackageNotFoundError:
        __version__ = "dev"
except ImportError:
    __version__ = "dev"
_USER_AGENT  = f"Ghostbit-CLI/{__version__}"

# Build an SSL context that works on macOS (certifi) and everywhere else.
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

LANGUAGES = [
    "python", "javascript", "typescript", "go", "rust", "ruby", "php",
    "java", "c", "cpp", "csharp", "bash", "powershell", "html", "css",
    "sql", "json", "yaml", "toml", "xml", "markdown", "dockerfile",
    "kotlin", "swift", "lua", "r", "diff",
]

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes as _hashes
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False


# ── Crypto (mirrors e2e.js) ───────────────────────────────────────────────────

def _require_crypto():
    if not _CRYPTO_OK:
        print("Error: 'cryptography' package required. Run: pip install cryptography", file=sys.stderr)
        sys.exit(1)

def _gen_key() -> bytes:
    return os.urandom(32)

def _gen_salt() -> str:
    return base64.b64encode(os.urandom(16)).decode()

def _encrypt(plaintext: str, key: bytes) -> tuple[str, str]:
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(ct).decode(), base64.b64encode(nonce).decode()

def _decrypt(ciphertext_b64: str, nonce_b64: str, key: bytes) -> str:
    ct    = base64.b64decode(ciphertext_b64)
    nonce = base64.b64decode(nonce_b64)
    pt    = AESGCM(key).decrypt(nonce, ct, None)
    return pt.decode()

def _derive_key(password: str, salt_b64: str) -> bytes:
    salt = base64.b64decode(salt_b64)
    kdf  = PBKDF2HMAC(algorithm=_hashes.SHA256(), length=32, salt=salt, iterations=600_000)
    return kdf.derive(password.encode())

def _key_to_fragment(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).rstrip(b'=').decode()

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH  = Path.home() / ".config" / "ghostbit.toml"
HISTORY_PATH = Path.home() / ".local" / "share" / "ghostbit" / "history.jsonl"
DEFAULT_SERVER = "http://localhost:8000"

VALID_KEYS = {"server"}


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    cfg = {}
    for line in CONFIG_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            cfg[key.strip()] = val.strip().strip('"').strip("'")
    return cfg


def _write_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'{k} = "{v}"' for k, v in cfg.items()]
    CONFIG_PATH.write_text("\n".join(lines) + "\n")


# ── Subcommands ───────────────────────────────────────────────────────────────

def _run_config(argv):
    parser = argparse.ArgumentParser(prog="gbit config", description="Manage Ghostbit CLI configuration.")
    sub = parser.add_subparsers(dest="action")

    sub.add_parser("show", help="Show current configuration.")

    p_set = sub.add_parser("set", help="Set a config value.")
    p_set.add_argument("key", help="Config key (e.g. server)")
    p_set.add_argument("value", help="Value to set")

    p_unset = sub.add_parser("unset", help="Remove a config key.")
    p_unset.add_argument("key", help="Config key to remove")

    args = parser.parse_args(argv)
    if not args.action:
        parser.print_help()
        sys.exit(0)
    cmd_config(args.action, getattr(args, "key", None), getattr(args, "value", None))


def cmd_config(action, key=None, value=None):
    cfg = _load_config()

    if action == "show":
        if not cfg:
            print(f"No config yet. File would be: {CONFIG_PATH}", file=sys.stderr)
            print(f"server = {DEFAULT_SERVER!r}  (default)")
        else:
            print(f"# {CONFIG_PATH}")
            for k, v in cfg.items():
                print(f"{k} = {v!r}")
        return

    if action == "set":
        k = key.lower()
        if k not in VALID_KEYS:
            print(f"Unknown config key {k!r}. Valid keys: {', '.join(VALID_KEYS)}", file=sys.stderr)
            sys.exit(1)
        cfg[k] = value
        _write_config(cfg)
        print(f"Set {k} = {value!r}")
        print(f"Config saved to {CONFIG_PATH}")
        return

    if action == "unset":
        k = key.lower()
        if k in cfg:
            del cfg[k]
            _write_config(cfg)
            print(f"Removed {k!r} from config.")
        else:
            print(f"{k!r} is not set.", file=sys.stderr)
        return


def cmd_paste(args):
    cfg = _load_config()
    server = args.server or cfg.get("server", DEFAULT_SERVER)

    # Read content
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        content = path.read_text(errors="replace")
        # Infer language from extension if not specified
        if args.lang is None:
            ext_map = {
                ".py": "python", ".js": "javascript", ".ts": "typescript",
                ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
                ".java": "java", ".c": "c", ".cpp": "cpp", ".cs": "csharp",
                ".sh": "bash", ".bash": "bash", ".zsh": "bash",
                ".html": "html", ".css": "css", ".sql": "sql",
                ".json": "json", ".yaml": "yaml", ".yml": "yaml",
                ".toml": "toml", ".xml": "xml", ".md": "markdown",
                ".dockerfile": "dockerfile", ".kt": "kotlin", ".swift": "swift",
                ".lua": "lua", ".r": "r", ".diff": "diff", ".patch": "diff",
            }
            # Handle extensionless files by name (e.g. Dockerfile, Makefile)
            name_map = {
                "dockerfile": "dockerfile", "makefile": "makefile",
            }
            args.lang = ext_map.get(path.suffix.lower()) or name_map.get(path.name.lower())
    else:
        if sys.stdin.isatty():
            print("Reading from stdin… (Ctrl+D to finish)", file=sys.stderr)
        content = sys.stdin.read()

    if not content.strip():
        print("Error: content is empty.", file=sys.stderr)
        sys.exit(1)

    _require_crypto()

    # ── Encrypt client-side (mirrors browser e2e.js) ──
    # If --password was given without a value, prompt interactively
    password = args.password
    if password is True or password == '':
        password = getpass.getpass('Password: ')
        if not password:
            print('Error: password cannot be empty.', file=sys.stderr)
            sys.exit(1)

    if password:
        kdf_salt = _gen_salt()
        key      = _derive_key(password, kdf_salt)
    else:
        key      = _gen_key()
        kdf_salt = None

    ciphertext, nonce = _encrypt(content, key)

    payload = {
        "content":     ciphertext,
        "nonce":       nonce,
        "kdf_salt":    kdf_salt,
        "language":    args.lang,
        "expires_in":  args.expires,
        "burn":        args.burn,
        "max_views":   args.max_views,
    }

    result = _api_create(server, payload)

    # Build full URL with fragment (key + delete token)
    if password:
        fragment = f"~{result['delete_token']}"
    else:
        fragment = f"{_key_to_fragment(key)}~{result['delete_token']}"

    full_url = f"{result['url']}#{fragment}"

    # Append to local history (best-effort, privacy-first — stays on disk only)
    if not args.no_history:
        _history_append({
            "id":         result["id"],
            "url":        result["url"],
            "full_url":   full_url,
            "created_at": int(time.time()),
            "language":   args.lang,
            "expires_at": result.get("expires_at"),
        })

    if args.json:
        result["full_url"] = full_url
        print(json.dumps(result, indent=2))
    elif args.quiet:
        print(full_url)
    else:
        print(full_url)
        if sys.stdout.isatty():
            parts = []
            if result.get("expires_at"):
                delta = result["expires_at"] - int(time.time())
                if delta < 3600:
                    parts.append(f"expires in {delta // 60}m")
                elif delta < 86400:
                    parts.append(f"expires in {delta // 3600}h")
                else:
                    parts.append(f"expires in {delta // 86400}d")
            if result.get("burn"):
                parts.append("burn after read")
            if result.get("max_views"):
                parts.append(f"max {result['max_views']} views")
            if password:
                parts.append("password protected")
            if parts:
                print("  " + "  ·  ".join(parts), file=sys.stderr)
            if not password:
                print("  Share the full URL — the decryption key is in the #fragment.", file=sys.stderr)


def _print_highlighted(content: str, language: str | None) -> None:
    """Print content with terminal syntax highlighting.

    Markdown: rendered via rich (titles, bold, lists, code blocks…) if available.
    Other languages: syntax-highlighted via Pygments if available.
    Fallback: plain text.
    """
    if language == "markdown":
        try:
            from rich.console import Console
            from rich.markdown import Markdown
            Console().print(Markdown(content))
            return
        except ImportError:
            pass

    try:
        from pygments import highlight
        from pygments.formatters import TerminalTrueColorFormatter
        from pygments.lexers import TextLexer, get_lexer_by_name
        from pygments.util import ClassNotFound

        try:
            lexer = get_lexer_by_name(language) if language else TextLexer()
        except ClassNotFound:
            lexer = TextLexer()

        print(highlight(content, lexer, TerminalTrueColorFormatter(style="monokai")), end="")
        return
    except ImportError:
        pass

    print(content)


def cmd_view(args):
    from urllib.parse import urldefrag, urlparse

    url_no_frag, fragment = urldefrag(args.url)
    parsed   = urlparse(url_no_frag)
    server   = f"{parsed.scheme}://{parsed.netloc}"
    paste_id = parsed.path.strip("/")

    if not paste_id or not parsed.scheme:
        print("Error: invalid URL.", file=sys.stderr)
        sys.exit(1)

    # Fragment format: KEY_B64URL~DELETE_TOKEN  (no password)
    #                  ~DELETE_TOKEN             (password-protected)
    key_b64url = fragment.partition("~")[0]
    is_password = not key_b64url

    # Fetch paste metadata + ciphertext
    api_url = f"{server}/api/v1/pastes/{paste_id}"
    req = urllib.request.Request(api_url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            detail = json.loads(body).get("detail", body)
        except Exception:
            detail = body
        print(f"Error {e.code}: {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Could not connect to {server}: {e.reason}", file=sys.stderr)
        sys.exit(1)

    _require_crypto()

    # Derive or import decryption key
    if is_password:
        password = getpass.getpass("Password: ")
        kdf_salt = data.get("kdf_salt")
        if not kdf_salt:
            print("Error: no KDF salt — paste is not password-protected.", file=sys.stderr)
            sys.exit(1)
        key = _derive_key(password, kdf_salt)
    else:
        # Restore base64 padding stripped for URL safety
        padded = key_b64url + "=" * (-len(key_b64url) % 4)
        key = base64.urlsafe_b64decode(padded)

    try:
        plaintext = _decrypt(data["content"], data["nonce"], key)
    except Exception:
        print("Error: decryption failed — wrong key or corrupted paste.", file=sys.stderr)
        sys.exit(1)

    # Warn if this view just burned the paste
    burned = data.get("burn") or (
        data.get("max_views") and data.get("view_count", 0) >= data["max_views"]
    )
    if burned and sys.stderr.isatty():
        print("⚠️  This paste has been burned and is no longer available on the server.", file=sys.stderr)

    language = data.get("language")
    if sys.stdout.isatty():
        _print_highlighted(plaintext, language)
    else:
        print(plaintext, end="")


# ── API ───────────────────────────────────────────────────────────────────────

def _api_create(server: str, payload: dict) -> dict:
    url = server.rstrip("/") + "/api/v1/pastes"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            detail = json.loads(body).get("detail", body)
        except Exception:
            detail = body
        print(f"Error {e.code}: {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Could not connect to {server}: {e.reason}", file=sys.stderr)
        print(f"  Tip: run `gbit config set server <URL>` to set your server.", file=sys.stderr)
        sys.exit(1)


# ── Local history ────────────────────────────────────────────────────────────

def _history_append(entry: dict) -> None:
    """Append one entry to the local history file (JSONL, one JSON object per line)."""
    try:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # history is best-effort, never block a paste creation


def _history_load() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    entries = []
    for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def cmd_delete(url: str) -> None:
    from urllib.parse import urldefrag, urlparse

    url_no_frag, fragment = urldefrag(url)
    parsed   = urlparse(url_no_frag)
    server   = f"{parsed.scheme}://{parsed.netloc}"
    paste_id = parsed.path.strip("/")

    if not paste_id or not parsed.scheme:
        print("Error: invalid URL.", file=sys.stderr)
        sys.exit(1)

    # Fragment: KEY~DELETE_TOKEN  or  ~DELETE_TOKEN
    delete_token = fragment.partition("~")[2]
    if not delete_token:
        print("Error: delete token missing from URL fragment (expected KEY~TOKEN or ~TOKEN).", file=sys.stderr)
        sys.exit(1)

    api_url = f"{server}/api/v1/pastes/{paste_id}"
    req = urllib.request.Request(
        api_url,
        headers={"User-Agent": _USER_AGENT, "X-Delete-Token": delete_token},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX):
            pass
        print(f"Deleted {paste_id}.")
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("Error: invalid delete token.", file=sys.stderr)
        elif e.code == 404:
            print("Error: paste not found (already deleted or expired).", file=sys.stderr)
        else:
            print(f"Error {e.code}.", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Could not connect to {server}: {e.reason}", file=sys.stderr)
        sys.exit(1)


def cmd_list(clear: bool = False) -> None:
    if clear:
        if HISTORY_PATH.exists():
            HISTORY_PATH.unlink()
            print("History cleared.")
        else:
            print("No history file found.")
        return

    entries = _history_load()
    if not entries:
        print("No pastes in local history.", file=sys.stderr)
        print(f"  History file: {HISTORY_PATH}", file=sys.stderr)
        return

    now = int(time.time())

    def _age(ts: int) -> str:
        delta = now - ts
        if delta < 120:      return "just now"
        if delta < 3600:     return f"{delta // 60}m ago"
        if delta < 86400:    return f"{delta // 3600}h ago"
        return f"{delta // 86400}d ago"

    def _expiry(expires_at) -> str:
        if not expires_at:
            return "never"
        delta = expires_at - now
        if delta <= 0:       return "expired"
        if delta < 3600:     return f"in {delta // 60}m"
        if delta < 86400:    return f"in {delta // 3600}h"
        return f"in {delta // 86400}d"

    print(f"{'ID':<12} {'Lang':<14} {'Created':<12} {'Expires':<10}  URL")
    print("-" * 80)
    for e in reversed(entries):
        row_id      = e.get("id", "?")[:10]
        lang        = (e.get("language") or "plain")[:12]
        created     = _age(e.get("created_at", 0))
        expires     = _expiry(e.get("expires_at"))
        full_url    = e.get("full_url", e.get("url", ""))
        print(f"{row_id:<12} {lang:<14} {created:<12} {expires:<10}  {full_url}")


# ── Shell completion ──────────────────────────────────────────────────────────

_COMPLETION_BASH = r"""
# Ghostbit bash completion
# Usage: eval "$(gbit completion bash)"  or add to ~/.bashrc

_gb_completion() {
    local cur prev words cword
    _init_completion 2>/dev/null || {
        COMPREPLY=()
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
        words=("${COMP_WORDS[@]}")
        cword=$COMP_CWORD
    }

    local langs="LANGS_PLACEHOLDER"
    local main_opts="--lang --expires --burn --max-views --password --server --quiet --json -l -e -b -m -p -s -q"

    # Option argument completions
    case "$prev" in
        --lang|-l)    COMPREPLY=($(compgen -W "$langs" -- "$cur")); return ;;
        --server|-s)  COMPREPLY=($(compgen -W "http:// https://" -- "$cur")); return ;;
        --expires|-e|--max-views|-m|--password|-p) return ;;
    esac

    local subcmd="${words[1]}"

    case "$subcmd" in
        config)
            case "$cword" in
                2) COMPREPLY=($(compgen -W "show set unset" -- "$cur")) ;;
                3) [[ "${words[2]}" == "set" || "${words[2]}" == "unset" ]] \
                    && COMPREPLY=($(compgen -W "server" -- "$cur")) ;;
            esac
            return ;;
        completion)
            COMPREPLY=($(compgen -W "bash zsh fish" -- "$cur"))
            return ;;
        view) return ;;
    esac

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=($(compgen -W "config view delete list completion $main_opts" -- "$cur"))
        COMPREPLY+=($(compgen -f -- "$cur"))
    else
        COMPREPLY=($(compgen -W "$main_opts" -- "$cur"))
        COMPREPLY+=($(compgen -f -- "$cur"))
    fi
}

complete -o filenames -F _gb_completion gbit
complete -o filenames -F _gb_completion ghostbit
"""

_COMPLETION_ZSH = r"""
#compdef gbit ghostbit
# Ghostbit zsh completion
# Usage: eval "$(gbit completion zsh)"  or add to ~/.zshrc

_gb() {
    local langs=(LANGS_PLACEHOLDER)
    local main_opts=(
        '(-l --lang)'{-l,--lang}'[language hint]:language:('"${langs[*]}"')'
        '(-e --expires)'{-e,--expires}'[TTL in seconds]:seconds:'
        '(-b --burn)'{-b,--burn}'[delete after first view]'
        '(-m --max-views)'{-m,--max-views}'[delete after N views]:count:'
        '(-p --password)'{-p,--password}'[encrypt with password]:password:'
        '(-s --server)'{-s,--server}'[server URL]:url:'
        '(-q --quiet)'{-q,--quiet}'[print URL only]'
        '--json[print full JSON response]'
    )

    local state
    _arguments -C \
        '1: :->first' \
        '*: :->rest' && return 0

    case $state in
        first)
            _alternative \
                'subcommands:subcommand:((config\:"manage config" view\:"view a paste" delete\:"delete a paste" list\:"list local history" completion\:"shell completion"))' \
                "options: :_arguments ${main_opts[*]}" \
                'files:file:_files'
            ;;
        rest)
            case $words[2] in
                config)
                    case $CURRENT in
                        3) _values 'action' show set unset ;;
                        4) [[ $words[3] == (set|unset) ]] && _values 'key' server ;;
                    esac ;;
                view)      _nothing ;;
                completion) _values 'shell' bash zsh fish ;;
                *)         _arguments "${main_opts[@]}" && _files ;;
            esac
            ;;
    esac
}

_gb
"""

_COMPLETION_FISH = """
# Ghostbit fish completion
# Usage: gbit completion fish | source  or save to ~/.config/fish/completions/gbit.fish

set -l langs LANGS_PLACEHOLDER

# Disable file completion when a subcommand is active and not needed
function __gb_no_subcommand
    not __fish_seen_subcommand_from config view delete list completion
end

# Subcommands
complete -c gbit -f -n '__gb_no_subcommand' -a config     -d 'Manage configuration'
complete -c gbit -f -n '__gb_no_subcommand' -a view       -d 'View and decrypt a paste'
complete -c gbit -f -n '__gb_no_subcommand' -a delete     -d 'Delete a paste'
complete -c gbit -f -n '__gb_no_subcommand' -a list       -d 'List local paste history'
complete -c gbit -f -n '__gb_no_subcommand' -a completion -d 'Output shell completion script'

# config actions
complete -c gbit -f -n '__fish_seen_subcommand_from config' -a show  -d 'Show current config'
complete -c gbit -f -n '__fish_seen_subcommand_from config' -a set   -d 'Set a value'
complete -c gbit -f -n '__fish_seen_subcommand_from config' -a unset -d 'Remove a value'

# completion shells
complete -c gbit -f -n '__fish_seen_subcommand_from completion' -a bash -d 'Bash completion'
complete -c gbit -f -n '__fish_seen_subcommand_from completion' -a zsh  -d 'Zsh completion'
complete -c gbit -f -n '__fish_seen_subcommand_from completion' -a fish -d 'Fish completion'

# Main options
complete -c gbit -n '__gb_no_subcommand' -s l -l lang       -d 'Language hint'         -a "$langs"
complete -c gbit -n '__gb_no_subcommand' -s e -l expires    -d 'TTL in seconds'
complete -c gbit -n '__gb_no_subcommand' -s b -l burn       -d 'Delete after first view'
complete -c gbit -n '__gb_no_subcommand' -s m -l max-views  -d 'Delete after N views'
complete -c gbit -n '__gb_no_subcommand' -s p -l password   -d 'Encrypt with password'
complete -c gbit -n '__gb_no_subcommand' -s s -l server     -d 'Server URL'
complete -c gbit -n '__gb_no_subcommand' -s q -l quiet      -d 'Print URL only'
complete -c gbit -n '__gb_no_subcommand'      -l json       -d 'Print full JSON response'
"""


def cmd_completion(shell: str) -> None:
    langs_str = " ".join(LANGUAGES)
    templates = {
        "bash": _COMPLETION_BASH,
        "zsh":  _COMPLETION_ZSH,
        "fish": _COMPLETION_FISH,
    }
    script = templates[shell].replace("LANGS_PLACEHOLDER", langs_str)
    print(script.strip())


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # Route to config subcommand early so file paths aren't mistaken for subcommands
    if len(sys.argv) > 1 and sys.argv[1] == "config":
        _run_config(sys.argv[2:])
        return

    # Route to delete subcommand
    if len(sys.argv) > 1 and sys.argv[1] == "delete":
        if len(sys.argv) < 3:
            print("Usage: gbit delete <url>", file=sys.stderr)
            sys.exit(1)
        cmd_delete(sys.argv[2])
        return

    # Route to list subcommand
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        clear = "--clear" in sys.argv
        cmd_list(clear=clear)
        return

    # Route to completion subcommand
    if len(sys.argv) > 1 and sys.argv[1] == "completion":
        shells = ["bash", "zsh", "fish"]
        if len(sys.argv) < 3 or sys.argv[2] not in shells:
            print(f"Usage: gbit completion [{'|'.join(shells)}]", file=sys.stderr)
            sys.exit(1)
        cmd_completion(sys.argv[2])
        return

    # Route to view subcommand
    if len(sys.argv) > 1 and sys.argv[1] == "view":
        if len(sys.argv) < 3:
            print("Usage: gbit view <url>", file=sys.stderr)
            sys.exit(1)
        view_parser = argparse.ArgumentParser(prog="gbit view")
        view_parser.add_argument("url", help="Full paste URL (including #fragment).")
        cmd_view(view_parser.parse_args(sys.argv[2:]))
        return

    cfg = _load_config()
    current_server = cfg.get("server", DEFAULT_SERVER)

    parser = argparse.ArgumentParser(
        prog="gbit",
        description="Ghostbit CLI — create encrypted pastes from the terminal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
examples:
  cat main.py | gbit
  gbit main.py
  gbit main.py --lang python --burn
  gbit main.py --expires 3600 --password secret
  gbit view https://paste.example.com/abc123#KEY~TOKEN
  gbit config set server https://paste.example.com
  gbit config show

current server: {current_server}
        """,
    )

    # ── gbit [file] ──
    parser.add_argument(
        "file",
        nargs="?",
        help="File to paste. Reads from stdin if omitted.",
    )
    parser.add_argument(
        "--server", "-s",
        default=None,
        metavar="URL",
        help=f"Server URL for this invocation only (current: {current_server})",
    )
    parser.add_argument(
        "--lang", "-l",
        default=None,
        help="Language (e.g. python, javascript, go). Auto-detected if omitted.",
    )
    parser.add_argument(
        "--expires", "-e",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Expiry TTL in seconds (3600 = 1 h, 86400 = 1 d). Default: never.",
    )
    parser.add_argument(
        "--burn", "-b",
        action="store_true",
        help="Delete after the first view.",
    )
    parser.add_argument(
        "--max-views", "-m",
        type=int,
        default=None,
        metavar="N",
        help="Delete after N views.",
    )
    parser.add_argument(
        "--password", "-p",
        nargs="?",
        const=True,
        default=None,
        metavar="PASS",
        help="Encrypt with a password. Omit value to be prompted securely.",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Print only the URL.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full JSON response.",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Don't save this paste to local history.",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args()
    cmd_paste(args)


if __name__ == "__main__":
    main()
