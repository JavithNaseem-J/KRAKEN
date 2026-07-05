FROM python:3.12-slim AS base

RUN groupadd -r akea && useradd -r -g akea akea

WORKDIR /app

COPY pyproject.toml /shared/
COPY shared/ /shared/shared/
RUN pip install --no-cache-dir /shared/

COPY services/orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/orchestrator/ .

RUN chown -R akea:akea /app
USER akea

EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
