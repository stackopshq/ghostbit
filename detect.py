"""
Language detection using Pygments.

Returns a language slug compatible with the LANGUAGES list in main.py,
or None if detection confidence is too low.
"""

from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound

# Map Pygments lexer aliases → our language slugs
_ALIAS_MAP: dict[str, str] = {
    "bash":          "bash",
    "sh":            "bash",
    "shell":         "bash",
    "zsh":           "bash",
    "c":             "c",
    "cpp":           "cpp",
    "c++":           "cpp",
    "csharp":        "csharp",
    "c#":            "csharp",
    "css":           "css",
    "diff":          "diff",
    "patch":         "diff",
    "docker":        "dockerfile",
    "dockerfile":    "dockerfile",
    "go":            "go",
    "html":          "html",
    "java":          "java",
    "js":            "javascript",
    "javascript":    "javascript",
    "json":          "json",
    "kotlin":        "kotlin",
    "lua":           "lua",
    "make":          "makefile",
    "makefile":      "makefile",
    "markdown":      "markdown",
    "md":            "markdown",
    "php":           "php",
    "python":        "python",
    "python3":       "python",
    "py":            "python",
    "rb":            "ruby",
    "ruby":          "ruby",
    "rust":          "rust",
    "sql":           "sql",
    "swift":         "swift",
    "toml":          "toml",
    "ts":            "typescript",
    "typescript":    "typescript",
    "xml":           "xml",
    "yaml":          "yaml",
    "yml":           "yaml",
}

# Lexers that Pygments over-triggers on plain text
_NOISY_LEXERS = {"text only", "plain text", "tex", "restructuredtext"}

# Minimum content length — Pygments needs enough tokens to be confident
_MIN_LENGTH = 100


def detect_language(content: str) -> str | None:
    """Return a language slug or None if not confident enough."""
    if len(content.strip()) < _MIN_LENGTH:
        return None

    try:
        lexer = guess_lexer(content)
    except ClassNotFound:
        return None

    name = lexer.name.lower()

    if name in _NOISY_LEXERS:
        return None

    # Check aliases first, then the lexer name itself
    for alias in lexer.aliases:
        slug = _ALIAS_MAP.get(alias.lower())
        if slug:
            return slug

    slug = _ALIAS_MAP.get(name)
    if slug:
        return slug

    return None
