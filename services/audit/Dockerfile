# ── STAGE 1: Builder ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml /shared/
COPY shared/ /shared/shared/
RUN pip install --no-cache-dir /shared/

COPY services/audit/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── STAGE 2: Runner ────────────────────────────────────────────────
FROM python:3.12-slim AS runner

RUN groupadd -r kraken && useradd -r -g kraken -s /sbin/nologin kraken

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=kraken:kraken services/audit/ .
RUN chown -R kraken:kraken /app

USER kraken

EXPOSE 8006
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os, httpx; port = os.getenv('PORT', '8006'); httpx.get(f'http://localhost:{port}/health').raise_for_status()"]
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8006}"]
