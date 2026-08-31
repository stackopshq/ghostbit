"""
Prometheus metrics for Ghostbit.

Exposed on GET /metrics (a plain route in main.py). The endpoint is open
by default, there are no per-paste details here, only aggregate counters
and histograms, and can be gated with METRICS_TOKEN, or restricted to
the scraper's IP at the reverse proxy.

Design choice: we hand-roll the counters instead of using a broad
instrumentation library so the metric names stay stable across fastapi
version bumps and the cardinality is bounded (no unbounded labels like
raw URLs).
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

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

# ── SQLite pool ─────────────────────────────────────────────────────────────

sqlite_pool_wait_seconds = Histogram(
    "ghostbit_sqlite_pool_wait_seconds",
    "Time a storage call spent waiting for a free SQLite connection. A non-zero "
    "P99 means the pool is a bottleneck: raise SQLITE_POOL_SIZE.",
    # 10 µs … 1 s; anything above 100 ms means serious contention.
    buckets=(0.00001, 0.0001, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
)

__all__ = [
    "CONTENT_TYPE_LATEST",
    "generate_latest",
    "http_request_duration_seconds",
    "pastes_created_total",
    "pastes_deleted_total",
    "pastes_viewed_total",
    "sqlite_pool_wait_seconds",
    "webhook_deliveries_total",
]
