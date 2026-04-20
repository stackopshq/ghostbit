"""
Language detection.

Two-stage strategy:
  1. Regex patterns for clear syntactic markers (fires from 30 chars).
  2. Pygments heuristic for longer content (100+ chars) as fallback.

Returns a language slug compatible with the LANGUAGES list in main.py,
or None if not confident enough.
"""

import re

from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound

# Ordered list of (language_slug, compiled_pattern).
# Patterns look for strong, unambiguous markers — NOT generic keywords.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Shebangs
    ("bash", re.compile(r"^#!\s*/(?:usr/)?(?:local/)?bin/(?:bash|sh|zsh)", re.M)),
    # JSON — starts with { or [ followed by quoted key or value
    ("json", re.compile(r'^\s*[\[{]\s*\n?\s*"', re.M)),
    # HTML
    ("html", re.compile(r"<!DOCTYPE\s+html|<html[\s>]|<head[\s>]|<body[\s>]", re.I)),
    # SQL — SELECT/INSERT/UPDATE/DELETE + FROM/INTO/SET
    ("sql", re.compile(r"\b(?:SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b", re.I)),
    # CSS — require known CSS properties to avoid false positives
    (
        "css",
        re.compile(
            r"\b(?:color|margin|padding|font-|background|display|border|width|height|flex|grid)\s*:",
            re.I,
        ),
    ),
    # YAML front matter or key: value blocks
    ("yaml", re.compile(r"^---\s*\n|^[a-z_][a-z0-9_]*:\s+\S", re.M)),
    # TypeScript (must come before JavaScript — stricter markers)
    (
        "typescript",
        re.compile(
            r":\s*(?:string|number|boolean|void|any|never)\b|interface\s+\w+\s*\{|type\s+\w+\s*="
        ),
    ),
    # JavaScript
    (
        "javascript",
        re.compile(r"\bconsole\.[a-z]+\s*\(|require\s*\(|(?:const|let|var)\s+\w+\s*=|=>\s*[{\w]"),
    ),
    # Python
    (
        "python",
        re.compile(r"^\s*(?:def |class |import |from \w+ import |elif |@\w+)\b|print\s*\(", re.M),
    ),
    # Go
    ("go", re.compile(r"^package\s+\w+|^import\s+\"|\bfmt\.\w+\s*\(|func\s+\w+\s*\(", re.M)),
    # Rust (before CSS — brace syntax could confuse CSS pattern)
    ("rust", re.compile(r"\bfn\s+\w+\s*\(|let\s+mut\s+|use\s+std::|impl\s+\w+")),
    # Ruby
    (
        "ruby",
        re.compile(r"^\s*(?:def |end\b|require ['\"]|puts |attr_(?:accessor|reader|writer))", re.M),
    ),
    # Java / Kotlin (shared marker first, then disambiguate)
    ("java", re.compile(r"public\s+(?:static\s+)?(?:class|void|int|String)\b|System\.out\.print")),
    ("kotlin", re.compile(r"\bfun\s+\w+\s*\(|val\s+\w+\s*:|var\s+\w+\s*:|println\s*\(")),
    # Bash (non-shebang)
    ("bash", re.compile(r"^\s*(?:echo\s|export\s|if\s*\[|fi\b|source\s|curl\s|apt\s)", re.M)),
    # Dockerfile
    ("dockerfile", re.compile(r"^(?:FROM|RUN|CMD|EXPOSE|ENV|ADD|COPY|ENTRYPOINT|WORKDIR)\s", re.M)),
    # TOML
    ("toml", re.compile(r"^\[[\w.]+\]\s*$|^\w+\s*=\s*(?:true|false|\d+|\")", re.M)),
    # XML
    ("xml", re.compile(r"<\?xml\s|<[a-z][a-z0-9]*(?:\s[^>]*)?>.*</[a-z]", re.I | re.S)),
    # Markdown
    ("markdown", re.compile(r"^#{1,6}\s\w|^\*\*\w|\[.+\]\(.+\)|^[-*]\s\w", re.M)),
    # Diff / patch
    ("diff", re.compile(r"^(?:---|\+\+\+|@@\s+-\d+)", re.M)),
]

# Map Pygments lexer aliases → our language slugs (fallback for long content)
_ALIAS_MAP: dict[str, str] = {
    "bash": "bash",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "csharp": "csharp",
    "c#": "csharp",
    "css": "css",
    "diff": "diff",
    "patch": "diff",
    "docker": "dockerfile",
    "dockerfile": "dockerfile",
    "go": "go",
    "html": "html",
    "java": "java",
    "js": "javascript",
    "javascript": "javascript",
    "json": "json",
    "kotlin": "kotlin",
    "lua": "lua",
    "make": "makefile",
    "makefile": "makefile",
    "markdown": "markdown",
    "md": "markdown",
    "php": "php",
    "python": "python",
    "python3": "python",
    "py": "python",
    "rb": "ruby",
    "ruby": "ruby",
    "rust": "rust",
    "sql": "sql",
    "swift": "swift",
    "toml": "toml",
    "ts": "typescript",
    "typescript": "typescript",
    "xml": "xml",
    "yaml": "yaml",
    "yml": "yaml",
}

_NOISY_LEXERS = {"text only", "plain text", "tex", "restructuredtext"}
_PYGMENTS_MIN = 100


def detect_language(content: str) -> str | None:
    """Return a language slug or None if not confident enough."""
    text = content.strip()
    if not text:
        return None

    # Stage 1 — fast regex patterns (works from 30 chars)
    if len(text) >= 30:
        for slug, pattern in _PATTERNS:
            if pattern.search(text):
                return slug

    # Stage 2 — Pygments heuristic (needs more content)
    if len(text) < _PYGMENTS_MIN:
        return None

    try:
        lexer = guess_lexer(text)
    except ClassNotFound:
        return None

    name = lexer.name.lower()
    if name in _NOISY_LEXERS:
        return None

    for alias in lexer.aliases:
        slug = _ALIAS_MAP.get(alias.lower())
        if slug:
            return slug

    return _ALIAS_MAP.get(name)
