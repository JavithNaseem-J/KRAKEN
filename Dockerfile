FROM node:20-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend-react/package.json frontend-react/package-lock.json ./
RUN npm ci
COPY frontend-react/ ./
RUN npm run build

FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies into /app/.venv using the committed lockfile
RUN uv sync --no-dev --frozen

# ── STAGE 2: Runner ────────────────────────────────────────────────
FROM python:3.12-slim AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app" \
    PORT=8000

RUN groupadd -r kraken && useradd -r -g kraken -s /sbin/nologin kraken

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY --chown=kraken:kraken src/ /app/src/
COPY --chown=kraken:kraken data/ /app/data/
COPY --chown=kraken:kraken main.py /app/main.py
COPY --from=frontend-builder --chown=kraken:kraken /frontend/dist/ /app/frontend-react/dist/

RUN mkdir -p /app/data/workspace && chown -R kraken:kraken /app

USER kraken

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import os, httpx; port = os.getenv('PORT', '8000'); httpx.get(f'http://localhost:{port}/health').raise_for_status()"]

CMD ["sh", "-c", "exec uvicorn src.api.gateway:app --host 0.0.0.0 --port ${PORT:-8000}"]
