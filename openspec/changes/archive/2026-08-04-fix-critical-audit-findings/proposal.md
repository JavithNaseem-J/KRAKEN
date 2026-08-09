# Proposal: fix-critical-audit-findings

## Why

A staff-engineer technical audit (2026-08-04, `technical_audit.md`) found 9 critical defects in AKEA: a live LLM API key committed to the repo, a bypassable production guard for the default HITL service token, a replayable CSRF token in the approval flow, synchronous blocking I/O inside async services that collapses throughput and starves the bounded worker pool, an unbounded executor path on HITL approval callbacks that bypasses load shedding, and a docker-compose setup that can silently point production at a local ephemeral database. Findings C-7 (hybrid search) and C-8 (Ragas eval) are excluded — they are covered by the in-progress change `hybrid-search-rerank-postgres-tickets-ragas`. These defects expose the system to credential theft, forged approvals, denial of service under partial outage, and silent data loss; they must be remediated before the system can be considered production-safe.

## What Changes

- **C-1 — Committed live API key**: Remove the live `LLM_API_KEY` from `.env`, rotate the key, document the secrets-manager-only policy, and add a pre-commit secret-scanning hook (`gitleaks` or `detect-secrets`) to block future leaks.
- **C-2 — HITL token guard bypassable**: Make the default-token validator unconditional — reject `"change-me-in-production"` and any token with insufficient entropy (`len < 32`) regardless of the `ENVIRONMENT` value, including when `ENVIRONMENT` is unset. **BREAKING** for dev setups that relied on the shipped default token; dev environments must set a unique token of >= 32 chars.
- **C-3 — CSRF token replay**: Consume the CSRF token atomically on verification (`redis.getdel()`) in `services/approval/queue.py` so a token cannot be replayed within its TTL window.
- **C-4 — Blocking sync Qdrant client in async service**: Migrate `SemanticCache` (`shared/cache.py`) to `qdrant_client.AsyncQdrantClient` with `async` `get()`/`put()`, awaited by the orchestrator, so cache lookups never block the event loop.
- **C-5 — Thread-pool starvation on retry**: Eliminate `time.sleep()` retry blocking inside graph nodes that run on the bounded `ThreadPoolExecutor` — move to non-blocking async retry (`tenacity` with async support) or equivalently guarantee worker availability under worst-case retry load.
- **C-6 — Unbounded executor on approval callback**: Route `/approval-callback` graph resumptions through the same bounded `graph_executor` and `graph_semaphore` as `/run`, returning HTTP 503 when at capacity.
- **C-9 — Compose violates cloud-only constraint**: Guard `docker-compose.yml` as dev-only (`ENVIRONMENT=dev` on all services), add startup validation that services refuse non-dev operation against `localhost`/Docker-internal database hosts, and add a `docker-compose.prod.yml` override that takes all database URLs from environment variables with no defaults.

## Capabilities

### New Capabilities
- `secrets-management`: Policy and enforcement for API keys and service secrets — no secrets committed to source control, secrets sourced only from a secrets manager / environment, and pre-commit scanning that blocks accidental commits.

### Modified Capabilities
- `approval-security-guardrail`: Default HITL token rejection becomes unconditional (entropy-based, not environment-conditional); CSRF tokens must be atomically consumed on verification to prevent replay.
- `knowledge-cache`: The orchestrator semantic cache must use a non-blocking async Qdrant client so cache operations never stall the event loop.
- `orchestrator-concurrency-control`: Graph-node retries must not block worker-pool threads; HITL approval-callback resumptions must go through the same bounded executor and semaphore as `/run`.
- `docker-standardization`: Compose files must be dev-guarded, services must fail fast when pointed at local databases in non-dev environments, and a prod override must require all DB URLs from the environment.

## Impact

- **Code**: `.env` / `.env.example`, `.pre-commit-config.yaml`, `shared/config.py`, `shared/cache.py`, `services/approval/queue.py`, `services/orchestrator/main.py`, `services/orchestrator/graph/nodes/retriever.py`, `services/orchestrator/graph/nodes/executor.py`, `docker-compose.yml`, new `docker-compose.prod.yml`.
- **Dependencies**: adds `qdrant-client` async usage (already a dependency), `tenacity`, and a dev-only pre-commit hook tool (`gitleaks` or `detect-secrets`).
- **Operations**: the leaked Groq API key must be rotated out-of-band before/with deployment; dev environments must set a unique `HITL_SERVICE_TOKEN` (>= 32 chars); production deploys must use `docker-compose.prod.yml` (or equivalent) with all DB URLs supplied via environment.
- **Behavioral**: HTTP 503 may now be returned on `/approval-callback` under load (previously unbounded); startup will hard-fail on weak/default tokens in all environments.
