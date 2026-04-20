"""Persistent CLI configuration (~/.config/ghostbit.toml).

Tiny hand-rolled TOML parser/writer — the file only carries one key
today ("server"), so pulling in tomllib + tomli-w for a two-line format
would be overkill for a CLI that already minimizes dependencies.
"""

from __future__ import annotations

import sys
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "ghostbit.toml"
DEFAULT_SERVER = "http://localhost:8000"
VALID_KEYS = {"server"}


def load_config() -> dict:
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


def write_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'{k} = "{v}"' for k, v in cfg.items()]
    CONFIG_PATH.write_text("\n".join(lines) + "\n")


def cmd_config(action: str, key: str | None = None, value: str | None = None) -> None:
    cfg = load_config()

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
        assert key is not None and value is not None
        k = key.lower()
        if k not in VALID_KEYS:
            print(
                f"Unknown config key {k!r}. Valid keys: {', '.join(VALID_KEYS)}",
                file=sys.stderr,
            )
            sys.exit(1)
        cfg[k] = value
        write_config(cfg)
        print(f"Set {k} = {value!r}")
        print(f"Config saved to {CONFIG_PATH}")
        return

    if action == "unset":
        assert key is not None
        k = key.lower()
        if k in cfg:
            del cfg[k]
            write_config(cfg)
            print(f"Removed {k!r} from config.")
        else:
            print(f"{k!r} is not set.", file=sys.stderr)
        return
