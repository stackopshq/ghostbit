# ── Stage 1: build dependencies ──────────────────────────────────────────────
FROM python:3.14-alpine AS builder

# Build deps needed to compile cryptography (Rust/C) and other native packages
RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev cargo

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


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

RUN mkdir -p /data

# ── Runtime configuration ─────────────────────────────────────────────────────
ENV STORAGE_BACKEND=sqlite
ENV SQLITE_PATH=/data/ghostbit.db
ENV REDIS_URL=redis://localhost:6379
ENV MAX_PASTE_SIZE=524288
ENV PORT=8000

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -qO- http://localhost:${PORT}/healthz || exit 1

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
