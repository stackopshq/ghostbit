"""Ghostbit CLI entry point + public re-exports.

The CLI is laid out as a small package so the crypto, config, history,
HTTP, and completion concerns each live in their own focused module.
This `__init__` hosts the command handlers (`cmd_paste`, `cmd_view`,
`cmd_delete`, `cmd_list`) and the argparse wiring in `main()`.

Underscore-prefixed names at the bottom of this file are re-exports
kept for backwards compatibility with `tests/test_cli_crypto.py`, which
imports `_encrypt`/`_decrypt`/etc. directly from the `cli` module.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from ._api import SSL_CTX, USER_AGENT, api_create
from ._completion import cmd_completion as _cmd_completion_raw
from ._config import DEFAULT_SERVER, cmd_config, load_config
from ._crypto import (
    decrypt,
    derive_key,
    encrypt,
    gen_key,
    gen_salt,
    key_to_fragment,
    require_crypto,
)
from ._history import HISTORY_PATH, history_append, history_load

# Version used by --version output. Read from installed package metadata
# so bumping cli/pyproject.toml is the single knob.
try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    try:
        __version__ = _pkg_version("ghostbit-cli")
    except PackageNotFoundError:
        __version__ = "dev"
except ImportError:
    __version__ = "dev"


LANGUAGES = [
    "python", "javascript", "typescript", "go", "rust", "ruby", "php",
    "java", "c", "cpp", "csharp", "bash", "powershell", "html", "css",
    "sql", "json", "yaml", "toml", "xml", "markdown", "dockerfile",
    "kotlin", "swift", "lua", "r", "diff",
]  # fmt: skip


# ── gbit paste ───────────────────────────────────────────────────────────────


def cmd_paste(args) -> None:
    cfg = load_config()
    server = args.server or cfg.get("server", DEFAULT_SERVER)

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        content = path.read_text(errors="replace")
        # Infer language from extension if not specified.
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
            }  # fmt: skip
            # Handle extensionless files by name (e.g. Dockerfile, Makefile).
            name_map = {"dockerfile": "dockerfile", "makefile": "makefile"}
            args.lang = ext_map.get(path.suffix.lower()) or name_map.get(path.name.lower())
    else:
        if sys.stdin.isatty():
            print("Reading from stdin… (Ctrl+D to finish)", file=sys.stderr)
        content = sys.stdin.read()

    if not content.strip():
        print("Error: content is empty.", file=sys.stderr)
        sys.exit(1)

    require_crypto()

    # Encrypt client-side (mirrors browser e2e.js).
    # If --password was given without a value, prompt interactively.
    password = args.password
    if password is True or password == "":
        password = getpass.getpass("Password: ")
        if not password:
            print("Error: password cannot be empty.", file=sys.stderr)
            sys.exit(1)

    if password:
        kdf_salt = gen_salt()
        key = derive_key(password, kdf_salt)
    else:
        key = gen_key()
        kdf_salt = None

    ciphertext, nonce = encrypt(content, key)

    payload = {
        "content": ciphertext,
        "nonce": nonce,
        "kdf_salt": kdf_salt,
        "language": args.lang,
        "expires_in": args.expires,
        "burn": args.burn,
        "max_views": args.max_views,
    }

    result = api_create(server, payload)

    # Build full URL with fragment (key + delete token).
    if password:
        fragment = f"~{result['delete_token']}"
    else:
        fragment = f"{key_to_fragment(key)}~{result['delete_token']}"

    full_url = f"{result['url']}#{fragment}"

    # Append to local history (best-effort, privacy-first — stays on disk only).
    if not args.no_history:
        history_append(
            {
                "id": result["id"],
                "url": result["url"],
                "full_url": full_url,
                "created_at": int(time.time()),
                "language": args.lang,
                "expires_at": result.get("expires_at"),
            }
        )

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
                print(
                    "  Share the full URL — the decryption key is in the #fragment.",
                    file=sys.stderr,
                )


# ── gbit view ────────────────────────────────────────────────────────────────


def _print_highlighted(content: str, language: str | None) -> None:
    """Print content with terminal syntax highlighting.

    Markdown: rendered via rich if available.
    Other languages: Pygments with a true-color terminal formatter.
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


def cmd_view(args) -> None:
    from urllib.parse import urldefrag, urlparse

    url_no_frag, fragment = urldefrag(args.url)
    parsed = urlparse(url_no_frag)
    server = f"{parsed.scheme}://{parsed.netloc}"
    paste_id = parsed.path.strip("/")

    if not paste_id or not parsed.scheme:
        print("Error: invalid URL.", file=sys.stderr)
        sys.exit(1)

    # Fragment format: KEY_B64URL~DELETE_TOKEN  (no password)
    #                  ~DELETE_TOKEN             (password-protected)
    key_b64url = fragment.partition("~")[0]
    is_password = not key_b64url

    api_url = f"{server}/api/v1/pastes/{paste_id}"
    req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            detail = json.loads(body).get("detail", body)
        except Exception:  # noqa: BLE001
            detail = body
        print(f"Error {e.code}: {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Could not connect to {server}: {e.reason}", file=sys.stderr)
        sys.exit(1)

    require_crypto()

    if is_password:
        password = getpass.getpass("Password: ")
        kdf_salt = data.get("kdf_salt")
        if not kdf_salt:
            print("Error: no KDF salt — paste is not password-protected.", file=sys.stderr)
            sys.exit(1)
        key = derive_key(password, kdf_salt)
    else:
        # Restore base64 padding stripped for URL safety.
        padded = key_b64url + "=" * (-len(key_b64url) % 4)
        key = base64.urlsafe_b64decode(padded)

    try:
        plaintext = decrypt(data["content"], data["nonce"], key)
    except Exception:  # noqa: BLE001
        print("Error: decryption failed — wrong key or corrupted paste.", file=sys.stderr)
        sys.exit(1)

    # Warn if this view just burned the paste.
    burned = data.get("burn") or (
        data.get("max_views") and data.get("view_count", 0) >= data["max_views"]
    )
    if burned and sys.stderr.isatty():
        print(
            "⚠️  This paste has been burned and is no longer available on the server.",
            file=sys.stderr,
        )

    language = data.get("language")
    if sys.stdout.isatty():
        _print_highlighted(plaintext, language)
    else:
        print(plaintext, end="")


# ── gbit delete ──────────────────────────────────────────────────────────────


def cmd_delete(url: str) -> None:
    from urllib.parse import urldefrag, urlparse

    url_no_frag, fragment = urldefrag(url)
    parsed = urlparse(url_no_frag)
    server = f"{parsed.scheme}://{parsed.netloc}"
    paste_id = parsed.path.strip("/")

    if not paste_id or not parsed.scheme:
        print("Error: invalid URL.", file=sys.stderr)
        sys.exit(1)

    # Fragment: KEY~DELETE_TOKEN  or  ~DELETE_TOKEN
    delete_token = fragment.partition("~")[2]
    if not delete_token:
        print(
            "Error: delete token missing from URL fragment (expected KEY~TOKEN or ~TOKEN).",
            file=sys.stderr,
        )
        sys.exit(1)

    api_url = f"{server}/api/v1/pastes/{paste_id}"
    req = urllib.request.Request(
        api_url,
        headers={"User-Agent": USER_AGENT, "X-Delete-Token": delete_token},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=SSL_CTX):
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


# ── gbit list ────────────────────────────────────────────────────────────────


def cmd_list(clear: bool = False) -> None:
    if clear:
        if HISTORY_PATH.exists():
            HISTORY_PATH.unlink()
            print("History cleared.")
        else:
            print("No history file found.")
        return

    entries = history_load()
    if not entries:
        print("No pastes in local history.", file=sys.stderr)
        print(f"  History file: {HISTORY_PATH}", file=sys.stderr)
        return

    now = int(time.time())

    def _age(ts: int) -> str:
        delta = now - ts
        if delta < 120:
            return "just now"
        if delta < 3600:
            return f"{delta // 60}m ago"
        if delta < 86400:
            return f"{delta // 3600}h ago"
        return f"{delta // 86400}d ago"

    def _expiry(expires_at) -> str:
        if not expires_at:
            return "never"
        delta = expires_at - now
        if delta <= 0:
            return "expired"
        if delta < 3600:
            return f"in {delta // 60}m"
        if delta < 86400:
            return f"in {delta // 3600}h"
        return f"in {delta // 86400}d"

    print(f"{'ID':<12} {'Lang':<14} {'Created':<12} {'Expires':<10}  URL")
    print("-" * 80)
    for e in reversed(entries):
        row_id = e.get("id", "?")[:10]
        lang = (e.get("language") or "plain")[:12]
        created = _age(e.get("created_at", 0))
        expires = _expiry(e.get("expires_at"))
        full_url = e.get("full_url", e.get("url", ""))
        print(f"{row_id:<12} {lang:<14} {created:<12} {expires:<10}  {full_url}")


def cmd_completion(shell: str) -> None:
    """Thin wrapper over `_completion.cmd_completion` that injects LANGUAGES."""
    _cmd_completion_raw(shell, LANGUAGES)


# ── Config subcommand parser (local, calls into _config.cmd_config) ──────────


def _run_config(argv) -> None:
    parser = argparse.ArgumentParser(
        prog="gbit config", description="Manage Ghostbit CLI configuration."
    )
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


# ── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    # Route subcommands early so file paths aren't mistaken for them.
    if len(sys.argv) > 1 and sys.argv[1] == "config":
        _run_config(sys.argv[2:])
        return

    if len(sys.argv) > 1 and sys.argv[1] == "delete":
        if len(sys.argv) < 3:
            print("Usage: gbit delete <url>", file=sys.stderr)
            sys.exit(1)
        cmd_delete(sys.argv[2])
        return

    if len(sys.argv) > 1 and sys.argv[1] == "list":
        clear = "--clear" in sys.argv
        cmd_list(clear=clear)
        return

    if len(sys.argv) > 1 and sys.argv[1] == "completion":
        shells = ["bash", "zsh", "fish"]
        if len(sys.argv) < 3 or sys.argv[2] not in shells:
            print(f"Usage: gbit completion [{'|'.join(shells)}]", file=sys.stderr)
            sys.exit(1)
        cmd_completion(sys.argv[2])
        return

    if len(sys.argv) > 1 and sys.argv[1] == "view":
        if len(sys.argv) < 3:
            print("Usage: gbit view <url>", file=sys.stderr)
            sys.exit(1)
        view_parser = argparse.ArgumentParser(prog="gbit view")
        view_parser.add_argument("url", help="Full paste URL (including #fragment).")
        cmd_view(view_parser.parse_args(sys.argv[2:]))
        return

    cfg = load_config()
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

    parser.add_argument(
        "file",
        nargs="?",
        help="File to paste. Reads from stdin if omitted.",
    )
    parser.add_argument(
        "--server", "-s", default=None, metavar="URL",
        help=f"Server URL for this invocation only (current: {current_server})",
    )  # fmt: skip
    parser.add_argument(
        "--lang", "-l", default=None,
        help="Language (e.g. python, javascript, go). Auto-detected if omitted.",
    )  # fmt: skip
    parser.add_argument(
        "--expires", "-e", type=int, default=None, metavar="SECONDS",
        help="Expiry TTL in seconds (3600 = 1 h, 86400 = 1 d). Default: never.",
    )  # fmt: skip
    parser.add_argument(
        "--burn", "-b", action="store_true",
        help="Delete after the first view.",
    )  # fmt: skip
    parser.add_argument(
        "--max-views", "-m", type=int, default=None, metavar="N",
        help="Delete after N views.",
    )  # fmt: skip
    parser.add_argument(
        "--password", "-p", nargs="?", const=True, default=None, metavar="PASS",
        help="Encrypt with a password. Omit value to be prompted securely.",
    )  # fmt: skip
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Print only the URL.",
    )  # fmt: skip
    parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    parser.add_argument(
        "--no-history", action="store_true",
        help="Don't save this paste to local history.",
    )  # fmt: skip
    parser.add_argument(
        "--version", "-V", action="version", version=f"%(prog)s {__version__}",
    )  # fmt: skip

    args = parser.parse_args()
    cmd_paste(args)


# ── Backwards-compat re-exports for tests/test_cli_crypto.py ─────────────────
# These aliases keep `from cli import _encrypt, _decrypt, …` working after
# the move from a flat module to a package. Drop them once the tests are
# updated to the new names.
_encrypt = encrypt
_decrypt = decrypt
_gen_key = gen_key
_gen_salt = gen_salt
_derive_key = derive_key
_key_to_fragment = key_to_fragment


__all__ = [
    "LANGUAGES",
    "__version__",
    "cmd_completion",
    "cmd_config",
    "cmd_delete",
    "cmd_list",
    "cmd_paste",
    "cmd_view",
    "main",
]
