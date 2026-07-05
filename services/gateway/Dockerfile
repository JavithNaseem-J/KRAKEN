# ── STAGE 1: Builder ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system compilation dependencies if any package needs them
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment to copy as a clean single directory
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install shared library
COPY pyproject.toml /shared/
COPY shared/ /shared/shared/
RUN pip install --no-cache-dir /shared/

# Install service dependencies
COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── STAGE 2: Runner ────────────────────────────────────────────────
FROM python:3.12-slim AS runner

# Create a non-root system group and user
RUN groupadd -r akea && useradd -r -g akea -s /sbin/nologin akea

WORKDIR /app

# Copy the pre-built virtual environment from the builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy service source code and set owner to non-root user
COPY --chown=akea:akea services/gateway/ .

# Ensure the app dir is owned by the non-root user
RUN chown -R akea:akea /app

# Switch to the non-root user
USER akea

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
