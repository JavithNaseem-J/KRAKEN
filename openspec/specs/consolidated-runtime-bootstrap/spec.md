# consolidated-runtime-bootstrap Specification

## Purpose
TBD - created by syncing change remediate-audit-consolidation-debt.

## Requirements

### Requirement: Single-process startup initializes all subsystem state
When the application boots as a single process via `src.api.routes:app`, the gateway lifespan SHALL initialize the state of every subsystem it serves in-process — approval queue, audit store, short-term and long-term memory stores, knowledge retriever and embedder, action-service HTTP client, and the orchestrator graph — by entering each sub-application's lifespan. A sub-application whose lifespan fails SHALL be logged as degraded and SHALL NOT prevent the gateway from booting; `/ready` SHALL report each degraded subsystem by name.

#### Scenario: Standalone boot initializes subsystem state
- **WHEN** the gateway app starts via `uvicorn src.api.routes:app` with no other processes running
- **THEN** every sub-application's `app.state` (queue, store, short_term, long_term, client, retriever, http, agent_graph) is initialized and no internal request fails with an `AttributeError` for missing state

#### Scenario: Degraded subsystem does not block boot
- **WHEN** a sub-application lifespan raises during startup (e.g. Redis unreachable and fallback unavailable)
- **THEN** the gateway still starts, logs the degraded subsystem, and `/ready` returns 503 naming that subsystem while other subsystems remain operational

### Requirement: Internal calls MUST NOT require TCP listeners
All inter-subsystem calls within the single process SHALL be routed through the shared helper in `src/utils/http_client.py`, which resolves in-process ASGI transports for registered subsystem URLs. No code path SHALL issue a raw HTTP call to a subsystem URL (`orchestrator_url`, `knowledge_url`, `action_url`, `approval_url`, `memory_url`, `audit_url`) without the in-process short-circuit. The helper SHALL retry only on transport errors and 5xx responses; 4xx responses SHALL NOT be retried.

#### Scenario: Audit write succeeds standalone
- **WHEN** an action executes in standalone mode and `fire_audit_log` runs
- **THEN** the audit entry is persisted via the in-process audit app without any TCP connection attempt to a separate audit port

#### Scenario: Episodic memory search succeeds standalone
- **WHEN** the retriever node queries long-term memory in standalone mode
- **THEN** the request is served by the in-process memory app and returns results (or an empty list) instead of failing with connection refused

#### Scenario: Client error is not retried
- **WHEN** an internal call receives a 4xx response (e.g. 409 for an already-resolved approval)
- **THEN** the helper raises immediately after the first attempt without retrying

### Requirement: HITL approval endpoints reachable through the gateway in single-port mode
The gateway SHALL expose proxy routes for `GET /approve/{approval_id}/details` and `POST /approve/{approval_id}/decision` that forward to the in-process approval application, so the full HITL loop (interrupt → details + CSRF → decision → graph resume) works when only the gateway port is reachable.

#### Scenario: Browser completes approval via gateway only
- **WHEN** a CRITICAL action pauses the graph and the frontend calls `GET /approve/{id}/details` then `POST /approve/{id}/decision` against the gateway URL
- **THEN** both requests succeed, the graph resumes with the human decision, and no second port is required

### Requirement: Gateway /run/stream validation returns 422 on invalid payloads
The `/v1/run/stream` endpoint SHALL validate request bodies with the same schema as `/v1/run` and SHALL return HTTP 422 with a structured error for invalid payloads, never an unhandled `NameError`.

#### Scenario: Invalid payload on stream endpoint
- **WHEN** a client posts a body violating `QueryRequest` to `/v1/run/stream`
- **THEN** the response is HTTP 422 with an `error` field, and no 500 is produced
