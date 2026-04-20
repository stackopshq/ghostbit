"""
Single source of truth for language metadata consumed by the server side
(picker list in main.py, Pygments alias map in detect.py, CodeMirror mode
map + extension map in the HTML templates).

The CLI keeps its own copy of a subset in cli/cli.py because it ships as
a separately published package; a consistency test guards against drift.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_LANGUAGES_FILE = Path(__file__).with_name("languages.json")


@lru_cache(maxsize=1)
def _raw() -> list[dict]:
    with _LANGUAGES_FILE.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def slugs() -> list[str]:
    """Slugs in canonical order, prefixed with "" (the "no-highlight" entry
    the picker offers as a default)."""
    return [""] + [entry["slug"] for entry in _raw()]


@lru_cache(maxsize=1)
def codemirror_mode_map() -> dict[str, str | None]:
    """slug → CodeMirror 5 mode/MIME (None means 'no CM mode, plain text')."""
    out: dict[str, str | None] = {"": None}
    for entry in _raw():
        out[entry["slug"]] = entry["cm_mode"]
    return out


@lru_cache(maxsize=1)
def extension_map() -> dict[str, str]:
    """slug → preferred file extension used when downloading a paste.
    Slugs without any registered extension (e.g. makefile, dockerfile) map
    to the empty string so the caller knows to fall back to `.txt`."""
    out: dict[str, str] = {}
    for entry in _raw():
        exts = entry["extensions"]
        out[entry["slug"]] = exts[0] if exts else ""
    return out


@lru_cache(maxsize=1)
def pygments_alias_map() -> dict[str, str]:
    """Pygments lexer alias → our slug. Used by detect.py as the fallback
    stage after the regex patterns. Aliases are lower-cased."""
    out: dict[str, str] = {}
    for entry in _raw():
        for alias in entry["pygments_aliases"]:
            out[alias.lower()] = entry["slug"]
    return out
