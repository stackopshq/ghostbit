# ── Stage 1: build dependencies ──────────────────────────────────────────────
FROM python:3.14-alpine AS builder

# Build deps needed to compile cryptography (Rust/C) and other native packages
RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev cargo

WORKDIR /build

# Install third-party dependencies first so this layer caches independently
# of the app source (anything under app/ changes far more often than the
# requirements lock).
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Then install the server package itself — this is what makes
# `importlib.metadata.version("ghostbit")` work inside the final image
# (otherwise /openapi.json reports "0.0.0+source" even on tagged releases).
# `--no-deps` skips re-resolving the requirements we just installed.
COPY pyproject.toml README.md ./
COPY app/ ./app/
RUN pip install --no-cache-dir --prefix=/install --no-deps .


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.14-alpine

# ── OCI image annotations ─────────────────────────────────────────────────────
LABEL org.opencontainers.image.title="Ghostbit" \
      org.opencontainers.image.description="Self-hosted, end-to-end encrypted paste service" \
      org.opencontainers.image.url="https://github.com/stackopshq/ghostbit" \
      org.opencontainers.image.source="https://github.com/stackopshq/ghostbit" \
      org.opencontainers.image.documentation="https://docs.ghostbit.dev" \
      org.opencontainers.image.vendor="StackOps" \
      org.opencontainers.image.licenses="MIT"

# Runtime deps only (no compiler, no Rust, no build tools)
RUN apk add --no-cache libffi openssl

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app
COPY . .

# Non-root runtime user. /data must be writable by this user for SQLite.
RUN addgroup -S ghostbit && adduser -S -G ghostbit -H -s /sbin/nologin ghostbit \
    && mkdir -p /data \
    && chown -R ghostbit:ghostbit /data /app

USER ghostbit

# ── Runtime configuration ─────────────────────────────────────────────────────
ENV STORAGE_BACKEND=sqlite
ENV SQLITE_PATH=/data/ghostbit.db
ENV REDIS_URL=redis://localhost:6379
ENV MAX_PASTE_SIZE=524288
ENV PORT=8000

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["sh", "-c", "wget -qO- http://localhost:${PORT}/healthz || exit 1"]

# JSON-array CMD (silences Dockerfile JSONArgsRecommended) + `exec` so the
# shell is replaced by uvicorn. Without exec, uvicorn would be a child of
# /bin/sh and `podman stop` / `docker stop` SIGTERM would be delivered to
# the shell, not uvicorn — that's ~10 s of wasted shutdown time and risks
# half-committed requests on containers with many workers.
#
# When TRUST_PROXY_HEADERS=true, we also turn on uvicorn's --proxy-headers
# so the access log and request.client.host reflect the real client IP
# forwarded by the reverse proxy — otherwise the logs are full of the
# proxy's internal IP which is useless for triage. Kept conditional so
# the flag never applies when the operator hasn't opted in; otherwise a
# client that speaks directly to the app could spoof their address.
CMD ["sh", "-c", "set -- --host 0.0.0.0 --port ${PORT}; [ \"$TRUST_PROXY_HEADERS\" = \"true\" ] && set -- \"$@\" --proxy-headers --forwarded-allow-ips=\"*\"; exec uvicorn app.main:app \"$@\""]
