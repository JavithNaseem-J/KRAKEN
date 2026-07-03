FROM python:3.12-slim AS base

# Security: non-root user
RUN groupadd -r akea && useradd -r -g akea akea

WORKDIR /app

# Install shared package first (layer-cached until shared/ changes)
COPY shared/ /shared/
RUN pip install --no-cache-dir /shared/

# Install service deps
COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY services/gateway/ .

RUN chown -R akea:akea /app
USER akea

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
