#!/usr/bin/env python3
"""
Ghostbit CLI — create pastes from the terminal.

Usage:
  cat file.py | gb
  gb file.py
  gb file.py --lang python --burn
  gb config set server https://paste.example.com
  gb config show
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

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

def _derive_key(password: str, salt_b64: str) -> bytes:
    salt = base64.b64decode(salt_b64)
    kdf  = PBKDF2HMAC(algorithm=_hashes.SHA256(), length=32, salt=salt, iterations=600_000)
    return kdf.derive(password.encode())

def _key_to_fragment(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).rstrip(b'=').decode()

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path.home() / ".config" / "ghostbit.toml"
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
    parser = argparse.ArgumentParser(prog="gb config", description="Manage Ghostbit CLI configuration.")
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
            args.lang = ext_map.get(path.suffix.lower())
    else:
        if sys.stdin.isatty():
            print("Reading from stdin… (Ctrl+D to finish)", file=sys.stderr)
        content = sys.stdin.read()

    if not content.strip():
        print("Error: content is empty.", file=sys.stderr)
        sys.exit(1)

    _require_crypto()

    # ── Encrypt client-side (mirrors browser e2e.js) ──
    if args.password:
        kdf_salt = _gen_salt()
        key      = _derive_key(args.password, kdf_salt)
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
    if args.password:
        fragment = f"~{result['delete_token']}"
    else:
        fragment = f"{_key_to_fragment(key)}~{result['delete_token']}"

    full_url = f"{result['url']}#{fragment}"

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
            if args.password:
                parts.append("password protected")
            if parts:
                print("  " + "  ·  ".join(parts), file=sys.stderr)
            if not args.password:
                print("  Share the full URL — the decryption key is in the #fragment.", file=sys.stderr)


# ── API ───────────────────────────────────────────────────────────────────────

def _api_create(server: str, payload: dict) -> dict:
    url = server.rstrip("/") + "/api/v1/pastes"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "Ghostbit-CLI/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
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
        print(f"  Tip: run `gb config set server <URL>` to set your server.", file=sys.stderr)
        sys.exit(1)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # Route to config subcommand early so file paths aren't mistaken for subcommands
    if len(sys.argv) > 1 and sys.argv[1] == "config":
        _run_config(sys.argv[2:])
        return

    cfg = _load_config()
    current_server = cfg.get("server", DEFAULT_SERVER)

    parser = argparse.ArgumentParser(
        prog="gb",
        description="Ghostbit CLI — create encrypted pastes from the terminal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
examples:
  cat main.py | gb
  gb main.py
  gb main.py --lang python --burn
  gb main.py --expires 3600 --password secret
  gb config set server https://paste.example.com
  gb config show

current server: {current_server}
        """,
    )

    # ── gb [file] ──
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
        default=None,
        metavar="PASS",
        help="Encrypt with a password.",
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

    args = parser.parse_args()
    cmd_paste(args)


if __name__ == "__main__":
    main()
