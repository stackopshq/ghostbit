"""Local, privacy-first paste history (~/.local/share/ghostbit/history.jsonl).

Every paste created by the CLI gets one JSONL line appended. The file
never leaves the user's machine: the CLI does not sync it anywhere:
and is only read by `gbit list` / `gbit list --clear`.

Each entry carries `full_url`, i.e. the URL *with* the `#key~token`
fragment: whoever reads this file can decrypt and delete every paste it
lists. It is therefore created 0600 in a 0700 directory, and both modes
are re-asserted on every append so a file created by an older CLI (which
used the umask default) gets tightened the first time it is touched.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

HISTORY_PATH = Path.home() / ".local" / "share" / "ghostbit" / "history.jsonl"


def history_append(entry: dict) -> None:
    """Append one entry; best-effort. Never block a paste creation on disk I/O."""
    try:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(HISTORY_PATH.parent, 0o700)
        fd = os.open(HISTORY_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        os.chmod(HISTORY_PATH, 0o600)
    # Intentional catch-all: history is a convenience, never a reason to
    # fail a paste.
    except Exception:  # noqa: BLE001
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
