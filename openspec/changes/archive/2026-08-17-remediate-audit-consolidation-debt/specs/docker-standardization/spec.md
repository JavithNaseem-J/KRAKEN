## MODIFIED Requirements

### Requirement: Service Dockerfiles Standardized
The repository SHALL ship a single application Dockerfile (renamed from `Dockerfile.standalone` to `Dockerfile`) that builds the consolidated KRAKEN app: it MUST use UTF-8 encoding, base on `python:3.12-slim`, install runtime dependencies from the exported `requirements.txt`, copy `src/`, `main.py`, and `data/`, run as a non-root user, define a `HEALTHCHECK` against `/health`, and start the app with `uvicorn src.api.routes:app` honoring the `PORT` environment variable. No Dockerfile SHALL reference the removed `services/` or `shared/` directories.

#### Scenario: Dockerfile build execution
- **WHEN** the application container is built with `docker build`
- **THEN** the build succeeds without character encoding warnings or missing dependencies, and the resulting image serves `/health` with HTTP 200

#### Scenario: Image contains no legacy service tree
- **WHEN** the built image filesystem is inspected
- **THEN** no `services/` or `shared/` directory is present and the entrypoint boots `src.api.routes:app`

### Requirement: Production compose override requires external configuration
A `docker-compose.prod.yml` override SHALL exist that: provisions no local `postgres` or `redis` containers; requires all database, cache, and vector-store URLs to be supplied via environment variables with no hardcoded defaults (using `${VAR:?message}` semantics so `docker compose up` fails fast when they are absent); and exposes the host port only for the consolidated application service (8000), with the HITL approval endpoints served through the gateway on that same port.

#### Scenario: Prod stack started without required env vars
- **WHEN** an operator runs `docker compose -f docker-compose.yml -f docker-compose.prod.yml up` without setting `POSTGRES_URL` (or another required URL)
- **THEN** compose fails at startup with an error identifying the missing variable, rather than starting with a silent default

#### Scenario: Only the application port is host-exposed in prod
- **WHEN** the prod override is applied
- **THEN** only port 8000 (consolidated app) is published to the host, and approval details/decision endpoints are reachable via gateway routes on that port
