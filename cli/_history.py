"""Local, privacy-first paste history (~/.local/share/ghostbit/history.jsonl).

Every paste created by the CLI gets one JSONL line appended. The file
never leaves the user's machine — the CLI does not sync it anywhere —
and is only read by `gbit list` / `gbit list --clear`.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

HISTORY_PATH = Path.home() / ".local" / "share" / "ghostbit" / "history.jsonl"


def history_append(entry: dict) -> None:
    """Append one entry; best-effort. Never block a paste creation on disk I/O."""
    try:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:  # noqa: BLE001 — intentional best-effort
        pass


def history_load() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    entries = []
    for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            with contextlib.suppress(json.JSONDecodeError):
                entries.append(json.loads(line))
    return entries
