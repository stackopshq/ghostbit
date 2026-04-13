"""Integration tests for the REST API."""

import base64
import os
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENCRYPTION_KEY", "a" * 64)
os.environ.setdefault("STORAGE_BACKEND", "sqlite")
# Use a temp file so tests work in any environment (CI has no /data/)
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["SQLITE_PATH"] = _tmp_db.name
_tmp_db.close()

from app.main import app
from app.storage import get_storage


@pytest_asyncio.fixture(scope="module")
async def client():
    # Manually initialize storage so lifespan side-effects are covered
    app.state.storage = await get_storage()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await app.state.storage.close()


def _fake_paste(**kwargs):
    key   = os.urandom(32)
    nonce = os.urandom(12)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    ct = AESGCM(key).encrypt(nonce, b"hello world", None)
    return {
        "content": base64.b64encode(ct).decode(),
        "nonce":   base64.b64encode(nonce).decode(),
        "burn":    False,
        **kwargs,
    }


@pytest.mark.anyio
async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.anyio
async def test_create_and_get_paste(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste())
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    assert "delete_token" in data

    r2 = await client.get(f"/api/v1/pastes/{data['id']}")
    assert r2.status_code == 200
    assert r2.json()["id"] == data["id"]


@pytest.mark.anyio
async def test_burn_after_read(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste(burn=True))
    paste_id = r.json()["id"]

    assert (await client.get(f"/api/v1/pastes/{paste_id}")).status_code == 200
    assert (await client.get(f"/api/v1/pastes/{paste_id}")).status_code == 404


@pytest.mark.anyio
async def test_max_views(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste(max_views=2))
    paste_id = r.json()["id"]

    assert (await client.get(f"/api/v1/pastes/{paste_id}")).status_code == 200
    assert (await client.get(f"/api/v1/pastes/{paste_id}")).status_code == 200
    assert (await client.get(f"/api/v1/pastes/{paste_id}")).status_code == 404


@pytest.mark.anyio
async def test_delete_with_valid_token(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste())
    data = r.json()
    r2 = await client.delete(
        f"/api/v1/pastes/{data['id']}",
        headers={"X-Delete-Token": data["delete_token"]},
    )
    assert r2.status_code == 204
    assert (await client.get(f"/api/v1/pastes/{data['id']}")).status_code == 404


@pytest.mark.anyio
async def test_delete_with_invalid_token(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste())
    r2 = await client.delete(
        f"/api/v1/pastes/{r.json()['id']}",
        headers={"X-Delete-Token": "wrongtoken"},
    )
    assert r2.status_code == 403


@pytest.mark.anyio
async def test_ssrf_webhook_blocked(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste(webhook_url="http://192.168.1.1/hook"))
    assert r.status_code == 400


@pytest.mark.anyio
async def test_content_too_large(client):
    payload = {
        "content": "A" * (1024 * 1024),
        "nonce":   base64.b64encode(os.urandom(12)).decode(),
    }
    r = await client.post("/api/v1/pastes", json=payload)
    assert r.status_code == 400


@pytest.mark.anyio
async def test_security_txt(client):
    r = await client.get("/.well-known/security.txt")
    assert r.status_code == 200
    assert "Contact:" in r.text
