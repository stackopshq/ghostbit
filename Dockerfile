FROM python:3.12-slim

# ── OCI image annotations ─────────────────────────────────────────────────────
LABEL org.opencontainers.image.title="Ghostbit" \
      org.opencontainers.image.description="Self-hosted, end-to-end encrypted paste service" \
      org.opencontainers.image.url="https://github.com/stackopshq/ghostbit" \
      org.opencontainers.image.source="https://github.com/stackopshq/ghostbit" \
      org.opencontainers.image.documentation="https://docs.ghostbit.dev" \
      org.opencontainers.image.vendor="StackOps HQ" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

# ── Runtime configuration ─────────────────────────────────────────────────────
# Storage backend: "sqlite" or "redis"
ENV STORAGE_BACKEND=sqlite

# SQLite database path (only used when STORAGE_BACKEND=sqlite)
ENV SQLITE_PATH=/data/ghostbit.db

# Redis connection URL (only used when STORAGE_BACKEND=redis)
ENV REDIS_URL=redis://localhost:6379

# Maximum paste size in bytes (default: 512 KB)
ENV MAX_PASTE_SIZE=524288

# Server port
ENV PORT=8000

EXPOSE ${PORT}

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
