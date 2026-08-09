# docker-standardization Delta Spec

## ADDED Requirements

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
A `docker-compose.prod.yml` override SHALL exist that: provisions no local `postgres` or `redis` containers; requires all database, cache, and service URLs to be supplied via environment variables with no hardcoded defaults (using `${VAR:?message}` semantics so `docker compose up` fails fast when they are absent); and exposes host ports only for the gateway (8000) and approval (8004) services, leaving all other services reachable only via the internal Docker network.

#### Scenario: Prod stack started without required env vars
- **WHEN** an operator runs `docker compose -f docker-compose.yml -f docker-compose.prod.yml up` without setting `POSTGRES_URL` (or another required URL)
- **THEN** compose fails at startup with an error identifying the missing variable, rather than starting with a silent default

#### Scenario: Internal services not host-exposed in prod
- **WHEN** the prod override is applied
- **THEN** only ports 8000 (gateway) and 8004 (approval) are published to the host; knowledge, memory, action, audit, and orchestrator services have no host port bindings
