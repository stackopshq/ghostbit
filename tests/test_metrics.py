"""Smoke + integration tests for the Prometheus metrics endpoint.

These run against the real FastAPI app (same ASGI transport as test_api.py)
to catch routing regressions (e.g. the /metrics mount accidentally shadowed
by a catch-all) and to verify that business counters actually increment on
user-visible actions.
"""

from __future__ import annotations

import base64
import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.storage import get_storage


@pytest.fixture(scope="module")
async def client():
    os.environ.setdefault("STORAGE_BACKEND", "sqlite")
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        os.environ["SQLITE_PATH"] = tmp.name

    from app.main import app  # local import so the env vars above take effect

    app.state.storage = await get_storage()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await app.state.storage.close()


def _encrypted_body(**kwargs):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = os.urandom(32)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, b"hello", None)
    return {
        "content": base64.b64encode(ct).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        **kwargs,
    }


async def test_metrics_endpoint_exposes_prometheus_format(client):
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    # Exposition format: every defined metric shows up with a HELP line.
    assert "ghostbit_pastes_created_total" in r.text
    assert "ghostbit_pastes_viewed_total" in r.text
    assert "ghostbit_pastes_deleted_total" in r.text
    assert "ghostbit_webhook_deliveries_total" in r.text
    assert "ghostbit_http_request_duration_seconds" in r.text


async def test_create_increments_counter(client):
    def created(metrics_text: str, has_password: str) -> float:
        for line in metrics_text.splitlines():
            if line.startswith(f'ghostbit_pastes_created_total{{has_password="{has_password}"}}'):
                return float(line.rsplit(maxsplit=1)[-1])
        return 0.0

    before = created((await client.get("/metrics")).text, "false")

    r = await client.post("/api/v1/pastes", json=_encrypted_body())
    assert r.status_code == 201

    after = created((await client.get("/metrics")).text, "false")
    assert after == before + 1


async def test_view_increments_counter_with_burn_label(client):
    """Counter is labelled by whether the view burned the paste. A normal
    GET on a non-burn paste increments burned="false"."""
    create = await client.post("/api/v1/pastes", json=_encrypted_body())
    paste_id = create.json()["id"]

    def viewed(text: str, burned: str) -> float:
        for line in text.splitlines():
            if line.startswith(f'ghostbit_pastes_viewed_total{{burned="{burned}"}}'):
                return float(line.rsplit(maxsplit=1)[-1])
        return 0.0

    before = viewed((await client.get("/metrics")).text, "false")
    r = await client.get(f"/api/v1/pastes/{paste_id}")
    assert r.status_code == 200
    after = viewed((await client.get("/metrics")).text, "false")
    assert after == before + 1


async def test_metrics_endpoint_does_not_recurse_into_latency_histogram(client):
    """The /metrics path is excluded from the latency histogram — otherwise
    every scrape would double as a data point and bias P99 heavily."""
    text = (await client.get("/metrics")).text
    # The path="/metrics" label must not appear in the latency histogram.
    for line in text.splitlines():
        if line.startswith("ghostbit_http_request_duration_seconds"):
            assert 'path="/metrics"' not in line
