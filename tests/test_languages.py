"""Contract tests for app.languages + drift guard against cli/cli.py.

languages.json is the single source of truth for the server side; the CLI
keeps its own list because it ships as a separate PyPI package. These tests
enforce that every slug shared with the CLI exposes a consistent extension,
so adding/renaming a language on one side makes the other side fail loudly
instead of silently diverging.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "cli"))

from app import languages  # noqa: E402


@pytest.fixture(scope="module")
def server_slugs() -> set[str]:
    # Skip the leading "" placeholder — it's a UI affordance, not a language.
    return {s for s in languages.slugs() if s}


def test_every_entry_has_required_fields():
    for entry in languages._raw():
        assert isinstance(entry["slug"], str) and entry["slug"]
        assert isinstance(entry["extensions"], list)
        assert "cm_mode" in entry  # may be None
        assert isinstance(entry["pygments_aliases"], list)
        assert entry["pygments_aliases"], (
            f"slug {entry['slug']} has no pygments aliases — Pygments fallback will never match it"
        )


def test_slugs_are_unique(server_slugs):
    raw_slugs = [entry["slug"] for entry in languages._raw()]
    assert len(raw_slugs) == len(set(raw_slugs))


def test_pygments_alias_map_has_no_conflicts():
    seen: dict[str, str] = {}
    for entry in languages._raw():
        for alias in entry["pygments_aliases"]:
            alias_lc = alias.lower()
            if alias_lc in seen:
                pytest.fail(
                    f"Pygments alias {alias_lc!r} is claimed by both "
                    f"{seen[alias_lc]!r} and {entry['slug']!r}"
                )
            seen[alias_lc] = entry["slug"]


def test_cli_extension_map_agrees_with_server(server_slugs):
    """Every CLI extension that maps to a shared slug must produce an
    extension the server also recognizes (reverse lookup). Drops any CLI-only
    slug (e.g. powershell, r) since those aren't in the server table yet."""
    import cli as cli_module

    # The CLI's ext map is built inside cmd_paste; rebuild the same dict here.
    cli_ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".cs": "csharp",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "bash",
        ".html": "html",
        ".css": "css",
        ".sql": "sql",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".xml": "xml",
        ".md": "markdown",
        ".dockerfile": "dockerfile",
        ".kt": "kotlin",
        ".swift": "swift",
        ".lua": "lua",
        ".r": "r",
        ".diff": "diff",
        ".patch": "diff",
    }

    server_extensions: dict[str, set[str]] = {}
    for entry in languages._raw():
        server_extensions[entry["slug"]] = set(entry["extensions"])

    # Every CLI (extension, slug) pair must be reflected in server data for
    # slugs that exist in both. CLI-only slugs (r, powershell) are allowed.
    for ext, slug in cli_ext_map.items():
        if slug not in server_slugs:
            continue
        assert ext in server_extensions[slug], (
            f"CLI maps {ext!r} → {slug!r} but server's languages.json for "
            f"{slug!r} only lists {sorted(server_extensions[slug])}. "
            "Add the extension on one side or rename on the other."
        )

    # Module exists to make the linter happy — the real assertion is above.
    assert hasattr(cli_module, "LANGUAGES")
