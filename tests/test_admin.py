"""Export/import CLI round-trip tests (SQLite backend)."""

import dataclasses
import io
import os
import tempfile

import pytest

os.environ.setdefault("STORAGE_BACKEND", "sqlite")
with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as _tmp_db:
    os.environ["SQLITE_PATH"] = _tmp_db.name

from app import admin  # noqa: E402
from app.storage import get_storage  # noqa: E402
from app.storage.base import PasteData  # noqa: E402


def _make_paste(pid: str, **overrides) -> PasteData:
    base = {
        "id": pid,
        "content": "Y2lwaGVydGV4dA==",
        "nonce": "bm9uY2UxMjM0NTY=",
        "kdf_salt": None,
        "language": "python",
        "created_at": 1_700_000_000,
        "expires_at": None,
        "burn": False,
        "has_password": False,
        "delete_token_hash": "0" * 64,
        "max_views": None,
        "view_count": 0,
        "webhook_url": None,
    }
    base.update(overrides)
    return PasteData(**base)


async def _seed(pastes):
    storage = await get_storage()
    try:
        for p in pastes:
            await storage.save(p)
    finally:
        await storage.close()


async def _wipe():
    storage = await get_storage()
    try:
        ids = [p.id async for p in storage.iter_all()]
        for pid in ids:
            await storage.force_delete(pid)
    finally:
        await storage.close()


async def _load_all():
    storage = await get_storage()
    try:
        return sorted(
            [dataclasses.asdict(p) async for p in storage.iter_all()],
            key=lambda d: d["id"],
        )
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_export_import_roundtrip():
    await _wipe()
    originals = [
        _make_paste("abc", language="python"),
        _make_paste("def", language="rust", burn=True),
        _make_paste("ghi", has_password=True, kdf_salt="c2FsdDEyMzQ1Njc4OTA="),
    ]
    await _seed(originals)

    buf = io.StringIO()
    n = await admin.export_all(buf)
    assert n == 3
    dump = buf.getvalue()
    assert dump.count("\n") == 3

    await _wipe()
    assert await _load_all() == []

    imported, skipped = await admin.import_all(io.StringIO(dump))
    assert imported == 3
    assert skipped == 0

    restored = await _load_all()
    expected = sorted([dataclasses.asdict(p) for p in originals], key=lambda d: d["id"])
    assert restored == expected


@pytest.mark.anyio
async def test_import_skips_existing_without_overwrite():
    await _wipe()
    original = _make_paste("dup", language="go", view_count=5)
    await _seed([original])

    # JSONL with the same ID but a different language + view_count
    mutated = dataclasses.asdict(original)
    mutated["language"] = "rust"
    mutated["view_count"] = 999
    import json as _json

    line = _json.dumps(mutated) + "\n"

    imported, skipped = await admin.import_all(io.StringIO(line))
    assert imported == 0
    assert skipped == 1

    # Original row must be untouched.
    storage = await get_storage()
    try:
        actual = await storage.get("dup")
        assert actual.language == "go"
        assert actual.view_count == 5
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_import_overwrite_replaces_existing():
    await _wipe()
    original = _make_paste("ow", language="go", view_count=5)
    await _seed([original])

    mutated = dataclasses.asdict(original)
    mutated["language"] = "rust"
    mutated["view_count"] = 42
    import json as _json

    line = _json.dumps(mutated) + "\n"

    imported, skipped = await admin.import_all(io.StringIO(line), overwrite=True)
    assert imported == 1
    assert skipped == 0

    storage = await get_storage()
    try:
        actual = await storage.get("ow")
        assert actual.language == "rust"
        assert actual.view_count == 42
    finally:
        await storage.close()


@pytest.mark.anyio
async def test_import_ignores_blank_lines():
    await _wipe()
    p = _make_paste("blank")
    import json as _json

    jsonl = "\n\n" + _json.dumps(dataclasses.asdict(p)) + "\n\n\n"
    imported, skipped = await admin.import_all(io.StringIO(jsonl))
    assert imported == 1
    assert skipped == 0


@pytest.mark.anyio
async def test_import_tolerates_unknown_fields():
    """A JSONL export from a future version that adds a column must still
    import cleanly on an older server — unknown fields are dropped with a
    warning, not treated as a fatal error."""
    await _wipe()
    record = dataclasses.asdict(_make_paste("fwd"))
    record["future_field"] = "hello"  # new column from a later version
    record["another_new"] = 42
    import json as _json

    line = _json.dumps(record) + "\n"

    imported, skipped = await admin.import_all(io.StringIO(line))
    assert imported == 1
    assert skipped == 0

    storage = await get_storage()
    try:
        actual = await storage.get("fwd")
        assert actual is not None
        assert actual.id == "fwd"
    finally:
        await storage.close()
