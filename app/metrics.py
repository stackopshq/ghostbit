"""
Prometheus metrics for Ghostbit.

Exposed on GET /metrics (mounted as an ASGI sub-app in main.py). The
endpoint is public by default — there are no per-paste details here,
only aggregate counters and histograms — but operators behind a proxy
can restrict it to the scraper's IP if they want.

Design choice: we hand-roll the counters instead of using a broad
instrumentation library so the metric names stay stable across fastapi
version bumps and the cardinality is bounded (no unbounded labels like
raw URLs).
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from prometheus_client import make_asgi_app as _make_asgi_app

# ── Business counters ────────────────────────────────────────────────────────

pastes_created_total = Counter(
    "ghostbit_pastes_created_total",
    "Pastes successfully created.",
    labelnames=("has_password",),
)

pastes_viewed_total = Counter(
    "ghostbit_pastes_viewed_total",
    "Paste ciphertext fetches via the JSON API (counted even if the view burns the paste).",
    labelnames=("burned",),
)

pastes_deleted_total = Counter(
    "ghostbit_pastes_deleted_total",
    "Paste deletions via a valid delete token (does not count implicit burns).",
)

webhook_deliveries_total = Counter(
    "ghostbit_webhook_deliveries_total",
    "Webhook delivery attempts, bucketed by terminal outcome.",
    labelnames=("outcome",),  # "ok" | "timeout" | "error" | "ssrf_blocked"
)

# ── HTTP latency ─────────────────────────────────────────────────────────────

http_request_duration_seconds = Histogram(
    "ghostbit_http_request_duration_seconds",
    "HTTP request latency in seconds, excluding /metrics and /healthz to avoid self-noise.",
    labelnames=("method", "path", "status"),
    # 1 ms … 10 s, covering a browser-facing HTML endpoint and a pathological slow case.
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# ── ASGI sub-app ─────────────────────────────────────────────────────────────

# Prometheus client ships an ASGI app that serves the exposition format.
# Mounted at /metrics from main.py.
asgi_app = _make_asgi_app()

__all__ = [
    "CONTENT_TYPE_LATEST",
    "asgi_app",
    "generate_latest",
    "http_request_duration_seconds",
    "pastes_created_total",
    "pastes_deleted_total",
    "pastes_viewed_total",
    "webhook_deliveries_total",
]
