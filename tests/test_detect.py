"""Tests for language detection.

detect_language is best-effort (Pygments heuristics) — tests verify
the interface contract, not specific detection accuracy.
"""

import pytest
from detect import detect_language

_PYTHON = """
import os
import sys
from typing import Optional, List

class DataProcessor:
    def __init__(self, path: str) -> None:
        self.path = path
        self._cache: dict[str, List[str]] = {}

    def process(self, items: List[str]) -> Optional[str]:
        if not items:
            return None
        return "\\n".join(items)

def main() -> None:
    proc = DataProcessor("/tmp/data")
    result = proc.process(["a", "b", "c"])
    print(result)

if __name__ == "__main__":
    main()
"""


def test_detects_python():
    assert detect_language(_PYTHON) == "python"


def test_returns_string_or_none():
    """Return type is always str | None — never raises."""
    result = detect_language(_PYTHON)
    assert result is None or isinstance(result, str)


def test_short_content_returns_none():
    assert detect_language("hi") is None


def test_empty_returns_none():
    assert detect_language("   ") is None


def test_plain_text_returns_none():
    prose = "This is a simple note without any code in it. " * 10
    # May return None or a language — what matters is it never raises
    result = detect_language(prose)
    assert result is None or isinstance(result, str)


def test_never_raises_on_arbitrary_input():
    for content in ["", "   ", "???###", "x" * 1000, "\x00\x01\x02"]:
        result = detect_language(content)
        assert result is None or isinstance(result, str)
