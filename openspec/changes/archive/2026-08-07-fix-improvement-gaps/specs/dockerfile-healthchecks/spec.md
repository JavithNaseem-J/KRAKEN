## ADDED Requirements

### Requirement: Application service Dockerfiles include HEALTHCHECK
All 7 service Dockerfiles SHALL include a `HEALTHCHECK` instruction that probes the service's `/health` endpoint. The check SHALL use Python+httpx (already installed) rather than curl.

#### Scenario: Healthy service passes Docker health check
- **WHEN** a service container is running and its `/health` endpoint returns HTTP 200
- **THEN** Docker reports the container status as `healthy`

#### Scenario: Unhealthy service fails Docker health check
- **WHEN** a service container is running but its `/health` endpoint is unreachable or returns non-200
- **THEN** Docker reports the container status as `unhealthy` after the configured retries
