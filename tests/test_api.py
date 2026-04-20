"""Integration tests for the REST API."""

import base64
import os
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("STORAGE_BACKEND", "sqlite")
# Use a temp file so tests work in any environment (CI has no /data/)
with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as _tmp_db:
    os.environ["SQLITE_PATH"] = _tmp_db.name

from app.main import app  # noqa: E402
from app.storage import get_storage  # noqa: E402


@pytest_asyncio.fixture(scope="module")
async def client():
    # Manually initialize storage so lifespan side-effects are covered
    app.state.storage = await get_storage()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await app.state.storage.close()


def _fake_paste(**kwargs):
    key = os.urandom(32)
    nonce = os.urandom(12)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ct = AESGCM(key).encrypt(nonce, b"hello world", None)
    return {
        "content": base64.b64encode(ct).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "burn": False,
        **kwargs,
    }


@pytest.mark.anyio
async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.anyio
async def test_csp_uses_nonce_not_unsafe_inline(client):
    """script-src must be nonce-based, not 'unsafe-inline'. A weakening
    of this header would silently re-enable XSS via any injection point."""
    r = await client.get("/")
    csp = r.headers.get("content-security-policy", "")
    assert "script-src" in csp
    # Extract the script-src directive
    script_src = next(d for d in csp.split(";") if d.strip().startswith("script-src"))
    assert "'nonce-" in script_src
    assert "'unsafe-inline'" not in script_src


@pytest.mark.anyio
async def test_csp_nonce_is_per_request(client):
    """Nonces must be unique per response — reuse would let an attacker
    who saw one nonce reuse it on later injections."""
    import re

    r1 = await client.get("/")
    r2 = await client.get("/")
    nonce_re = re.compile(r"'nonce-([^']+)'")
    n1 = nonce_re.search(r1.headers["content-security-policy"]).group(1)
    n2 = nonce_re.search(r2.headers["content-security-policy"]).group(1)
    assert n1 != n2
    # And the HTML must carry the same nonce as the header.
    assert f'nonce="{n1}"' in r1.text


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
async def test_delete_of_unknown_paste_also_returns_403(client):
    """The API must not distinguish 'paste exists with wrong token' from
    'paste does not exist' — otherwise an attacker can enumerate IDs by
    probing with an arbitrary token."""
    r = await client.delete(
        "/api/v1/pastes/doesnotexist",
        headers={"X-Delete-Token": "anything"},
    )
    assert r.status_code == 403


@pytest.mark.anyio
async def test_form_delete_of_unknown_paste_also_returns_403(client):
    """Same policy for the HTML form endpoint — the form is the legitimate
    owner path, but we still avoid leaking existence to anyone who can POST."""
    r = await client.post(
        "/doesnotexist/delete",
        data={"key": "anything"},
    )
    assert r.status_code == 403


@pytest.mark.anyio
async def test_ssrf_webhook_blocked(client):
    r = await client.post("/api/v1/pastes", json=_fake_paste(webhook_url="http://192.168.1.1/hook"))
    assert r.status_code == 400


@pytest.mark.anyio
async def test_content_too_large(client):
    payload = {
        "content": "A" * (1024 * 1024),
        "nonce": base64.b64encode(os.urandom(12)).decode(),
    }
    r = await client.post("/api/v1/pastes", json=payload)
    # 413 from the body-size middleware (hard HTTP ceiling) or 400 from the
    # application-level max_paste_size check — both are acceptable rejections.
    assert r.status_code in (400, 413)


@pytest.mark.anyio
async def test_security_txt(client):
    r = await client.get("/.well-known/security.txt")
    assert r.status_code == 200
    assert "Contact:" in r.text


@pytest.mark.anyio
async def test_id_collision_retry(client, monkeypatch):
    """When the random ID generator collides, create_paste should retry
    up to 8 times before giving up — it must never overwrite an existing paste."""
    # Force the generator to return a colliding ID twice, then a fresh one.
    import secrets as _secrets

    from app import api as api_mod

    first = await client.post("/api/v1/pastes", json=_fake_paste())
    assert first.status_code == 201
    taken_id = first.json()["id"]

    calls = {"n": 0}
    real_token_urlsafe = _secrets.token_urlsafe

    def fake_token_urlsafe(nbytes):
        # 6-byte tokens are only used for paste IDs; 16-byte ones are delete tokens.
        if nbytes == 6 and calls["n"] < 2:
            calls["n"] += 1
            return taken_id
        return real_token_urlsafe(nbytes)

    monkeypatch.setattr(api_mod.secrets, "token_urlsafe", fake_token_urlsafe)

    r = await client.post("/api/v1/pastes", json=_fake_paste())
    assert r.status_code == 201
    assert r.json()["id"] != taken_id
    assert calls["n"] == 2  # proves we actually retried past the collisions


@pytest.mark.anyio
async def test_security_headers_present(client):
    r = await client.get("/")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "no-referrer"
    assert "default-src 'self'" in r.headers.get("content-security-policy", "")
