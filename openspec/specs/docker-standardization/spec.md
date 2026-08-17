# docker-standardization Specification

## Purpose
Standardized container builds, compose configuration, and cloud-only environment guardrails.

## Requirements

### Requirement: Service Dockerfiles Standardized
The repository SHALL ship a single application Dockerfile (renamed from `Dockerfile.standalone` to `Dockerfile`) that builds the consolidated KRAKEN app: it MUST use UTF-8 encoding, base on `python:3.12-slim`, install runtime dependencies from the exported `requirements.txt`, copy `src/`, `main.py`, and `data/`, run as a non-root user, define a `HEALTHCHECK` against `/health`, and start the app with `uvicorn src.api.routes:app` honoring the `PORT` environment variable. No Dockerfile SHALL reference the removed `services/` or `shared/` directories.

#### Scenario: Dockerfile build execution
- **WHEN** the application container is built with `docker build`
- **THEN** the build succeeds without character encoding warnings or missing dependencies, and the resulting image serves `/health` with HTTP 200

#### Scenario: Image contains no legacy service tree
- **WHEN** the built image filesystem is inspected
- **THEN** no `services/` or `shared/` directory is present and the entrypoint boots `src.api.routes:app`

### Requirement: Render deployment specifications include health check probes and appropriate service tiers
In `render.yaml`, every web service entry SHALL declare a `healthCheckPath: /health` property. Critical services (including `akea-orchestrator` and `akea-approval`) SHALL specify `plan: starter` to prevent cold-start delays during Human-in-the-Loop workflows.

#### Scenario: Render routes traffic after health check passes
- **WHEN** a service deploys on Render
- **THEN** traffic is routed to the service instance only after its `/health` probe returns HTTP 200 OK

#### Scenario: HITL approval flow unaffected by cold start
- **WHEN** an approval callback is executed against the `akea-approval` service
- **THEN** the service is active on the `starter` plan and responds immediately without sleeping/cold-start latency

### Requirement: Compose services explicitly declare the dev environment
Every service in `docker-compose.yml` SHALL set `ENVIRONMENT=dev` in its environment block. The local `postgres` and `redis` containers in `docker-compose.yml` are a development convenience only and SHALL NOT be referenced by any non-development configuration.

#### Scenario: Service started via compose runs as dev
- **WHEN** the stack is started with `docker compose up` using the base `docker-compose.yml`
- **THEN** every application service has `ENVIRONMENT=dev` in its environment, making the dev-only nature of the local databases explicit

### Requirement: Non-dev startup rejects local database endpoints
When `environment` is not `"dev"`, service startup SHALL fail fast with a clear error if `postgres_url`, `redis_url`, or inter-service URLs point at local or Docker-internal hosts (`localhost`, `127.0.0.1`, or the compose service names `postgres`/`redis`). Validation SHALL occur in `shared/config.py` settings validation so all 7 services inherit it.

#### Scenario: Production config pointing at localhost Postgres
- **WHEN** a service starts with `ENVIRONMENT=prod` and `POSTGRES_URL` containing `localhost` or `postgres:5432`
- **THEN** settings validation raises a `ValueError` naming the offending setting and the process exits before accepting requests

#### Scenario: Production config with cloud endpoints
- **WHEN** a service starts with `ENVIRONMENT=prod` and all database/cache URLs point at cloud hosts (e.g., Supabase, Upstash)
- **THEN** settings validation passes and the service starts normally

#### Scenario: Dev environment unaffected
- **WHEN** a service starts with `ENVIRONMENT=dev` and local Docker-internal database URLs
- **THEN** settings validation passes (local endpoints are permitted only in dev)

### Requirement: Production compose override requires external configuration
A `docker-compose.prod.yml` override SHALL exist that: provisions no local `postgres` or `redis` containers; requires all database, cache, and vector-store URLs to be supplied via environment variables with no hardcoded defaults (using `${VAR:?message}` semantics so `docker compose up` fails fast when they are absent); and exposes the host port only for the consolidated application service (8000), with the HITL approval endpoints served through the gateway on that same port.

#### Scenario: Prod stack started without required env vars
- **WHEN** an operator runs `docker compose -f docker-compose.yml -f docker-compose.prod.yml up` without setting `POSTGRES_URL` (or another required URL)
- **THEN** compose fails at startup with an error identifying the missing variable, rather than starting with a silent default

#### Scenario: Only the application port is host-exposed in prod
- **WHEN** the prod override is applied
- **THEN** only port 8000 (consolidated app) is published to the host, and approval details/decision endpoints are reachable via gateway routes on that port

### Requirement: Docker Compose services depend on application health checks
In `docker-compose.yml`, application service dependencies SHALL specify `{ condition: service_healthy }` for upstream application services that define `HEALTHCHECK`.

#### Scenario: Compose waits for service health
- **WHEN** `docker compose up` starts dependent microservices
- **THEN** downstream services wait until upstream application services report healthy status
