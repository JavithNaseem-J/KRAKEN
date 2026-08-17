# integration-test-gate Specification

## Purpose
TBD - created by syncing change remediate-audit-consolidation-debt.

## Requirements

### Requirement: Integration suite boots the consolidated application with real lifespans
The repository SHALL contain an integration test suite (pytest marker `integration`) that starts `src.api.routes:app` via `TestClient` with its real lifespan executed — no post-hoc mocking of `app.state` — using fakeredis and in-memory database fallbacks so the suite runs without external services or network access. The LLM boundary SHALL be mocked at `get_llm`.

#### Scenario: Integration suite runs offline
- **WHEN** CI executes `pytest tests/integration -m integration`
- **THEN** all tests pass with no running Postgres, Redis, Qdrant, or LLM endpoint and no network calls

#### Scenario: Lifespan-initialized state is exercised
- **WHEN** an integration test calls any subsystem endpoint through the gateway
- **THEN** the request is served by state created during the real lifespan (approval queue, audit store, memory stores, retriever), proving initialization works end to end

### Requirement: End-to-end HITL flow is covered by the integration gate
The integration suite SHALL verify the complete human-in-the-loop cycle in standalone mode: a query producing a CRITICAL action returns `pending_approval` with an `approval_id`; `GET /approve/{id}/details` returns the payload and a CSRF token; `POST /approve/{id}/decision` with that token resumes the graph; and the final response reflects the approved action result.

#### Scenario: Approve path resumes the graph
- **WHEN** the suite submits a query whose mocked decider selects a CRITICAL action, fetches approval details, and posts an `approve` decision with the CSRF token
- **THEN** the graph resumes, the action executes, and a subsequent status query returns a `QueryResponse` containing the action result

#### Scenario: Reject path cancels the action
- **WHEN** the suite posts a `reject` decision for a pending approval
- **THEN** the graph resumes with a cancellation result and the action is not executed

### Requirement: SSE streaming completion is covered by the integration gate
The integration suite SHALL verify that `POST /v1/run/stream` emits SSE events ending in a `done` event that carries the final response payload.

#### Scenario: Stream ends with done event
- **WHEN** the suite posts a valid query to `/v1/run/stream`
- **THEN** the event stream terminates with a `done` event whose payload includes the `QueryResponse`

### Requirement: CI runs the integration gate plus static checks
The CI workflow SHALL run the integration suite, `mypy src/`, and the frontend lint as required checks on every pull request, in addition to unit tests and the frontend build.

#### Scenario: Pull request blocked by failing integration test
- **WHEN** a change breaks the consolidated runtime (e.g. a subsystem lifespan stops initializing state)
- **THEN** the CI integration job fails and the pull request cannot merge
