"""Admin CLI — export / import pastes for backup or cross-backend migration.

The CLI reads the same config as the server (STORAGE_BACKEND, SQLITE_PATH /
REDIS_URL) so it targets whichever backend is currently active.

    python -m app.admin export > backup.jsonl
    python -m app.admin import < backup.jsonl
    python -m app.admin import --overwrite < backup.jsonl

Running against a live server is safe (reads are non-blocking, writes are
atomic per paste) but best avoided under heavy load. For cross-backend
migration, run export with the source config, then re-run with
STORAGE_BACKEND switched and feed the file to import.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
from typing import IO, Tuple

from .storage import get_storage
from .storage.base import PasteData


async def export_all(out: IO[str]) -> int:
    storage = await get_storage()
    try:
        count = 0
        async for paste in storage.iter_all():
            out.write(json.dumps(dataclasses.asdict(paste), separators=(",", ":")))
            out.write("\n")
            count += 1
        return count
    finally:
        await storage.close()


async def import_all(src: IO[str], *, overwrite: bool = False) -> Tuple[int, int]:
    storage = await get_storage()
    try:
        imported = skipped = 0
        for raw in src:
            raw = raw.strip()
            if not raw:
                continue
            data = json.loads(raw)
            paste = PasteData(**data)
            if overwrite:
                await storage.force_delete(paste.id)
            if await storage.save(paste):
                imported += 1
            else:
                skipped += 1
        return imported, skipped
    finally:
        await storage.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.admin",
        description="Export or import Ghostbit pastes as JSONL.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export", help="Dump all pastes as JSONL to stdout.")
    imp = sub.add_parser("import", help="Load JSONL pastes from stdin.")
    imp.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing IDs instead of skipping them.",
    )
    args = parser.parse_args()

    if args.cmd == "export":
        n = asyncio.run(export_all(sys.stdout))
        print(f"Exported {n} paste(s).", file=sys.stderr)
    else:
        imported, skipped = asyncio.run(
            import_all(sys.stdin, overwrite=args.overwrite)
        )
        print(
            f"Imported {imported} paste(s), skipped {skipped} (already present).",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
