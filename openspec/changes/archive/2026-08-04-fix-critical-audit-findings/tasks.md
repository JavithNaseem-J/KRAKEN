# Tasks: fix-critical-audit-findings

## 1. Secrets Hygiene (C-1)

- [x] 1.1 Rotate the leaked Groq `LLM_API_KEY` at the provider (out-of-band operator action; confirm revocation before marking done)
- [x] 1.2 Scrub `.env`: replace the live `LLM_API_KEY` with a placeholder; audit `.env` for any other live credentials and replace with placeholders
- [x] 1.3 Create/update `.env.example` with placeholder values and comments stating secrets come only from environment/secrets manager (include a recipe for generating a >= 32-char `HITL_SERVICE_TOKEN`)
- [x] 1.4 Add `.pre-commit-config.yaml` with `gitleaks` (or `detect-secrets`) secret scanning and document `pre-commit install` in the README/onboarding docs
- [x] 1.5 Verify: run the secret scanner over the repo's tracked files and confirm no live credentials are reported

## 2. HITL Token Validation (C-2)

- [x] 2.1 In `shared/config.py`, rewrite `validate_production_secrets` to raise `ValueError` when `hitl_service_token == "change-me-in-production"` OR `len(hitl_service_token) < 32`, unconditionally (no environment check)
- [x] 2.2 Set a unique >= 32-char `HITL_SERVICE_TOKEN` in local/dev environment files (placeholder in `.env`, documented in `.env.example`)
- [x] 2.3 Add/update tests: default token fails in dev AND prod, short token fails, >= 32-char unique token passes

## 3. CSRF Replay Fix (C-3)

- [x] 3.1 In `services/approval/queue.py` `verify_csrf_token()`, replace `self._redis.get(...)` with `self._redis.getdel(...)` (atomic consume-on-verify)
- [x] 3.2 Add a regression test: a CSRF token that verifies once is rejected (403) on a second submission within the TTL window

## 4. Async Semantic Cache (C-4)

- [x] 4.1 In `shared/cache.py`, switch `SemanticCache` to `qdrant_client.AsyncQdrantClient`; remove network I/O from `__init__` and add an explicit `async def init()` that ensures the collection
- [x] 4.2 Make `get()` and `put()` `async` (await all client calls); preserve fail-open behavior (log + miss/skip on errors)
- [x] 4.3 In `services/orchestrator/main.py` lifespan, `await app.state.semantic_cache.init()`; update all cache call sites to `await cache.get()` / `await cache.put()`
- [x] 4.4 Update/add tests for the async cache (hit, miss, error fail-open, init creates collection)

## 5. Non-Blocking Graph Node Retries (C-5)

- [x] 5.1 Add `tenacity` to the orchestrator service dependencies
- [x] 5.2 Convert `retriever_node` (`graph/nodes/retriever.py`) to async: use `httpx.AsyncClient` and `tenacity` async retry (3 attempts, backoff, no `time.sleep`); preserve the graceful error result on exhaustion and the episodic-memory lookup behavior
- [x] 5.3 Convert `executor_node` (`graph/nodes/executor.py`) the same way (async client + async retry, no `time.sleep`)
- [x] 5.4 Switch graph invocation to `graph.ainvoke` in `/run` and `/approval-callback`; update module-level client lifecycle (create in lifespan / close on shutdown instead of module-level sync client)
- [x] 5.5 Add tests: no `time.sleep` in node retry paths; retries still produce the same external behavior (success after transient failure; graceful error after exhaustion)

## 6. Bounded Approval Callback (C-6)

- [x] 6.1 In `services/orchestrator/main.py` `approval_callback`, keep the `SELECT FOR UPDATE` idempotency transaction first, then acquire `app.state.graph_semaphore` via `semaphore.locked()` guard with HTTP 503 when at capacity, and resume via `ainvoke`, releasing the semaphore in `finally`
- [x] 6.2 Ensure the idempotency update is NOT committed as resolved when a 503 capacity rejection occurs (approval stays `pending` and retryable)
- [x] 6.3 Add tests: semaphore guard pattern; ainvoke used in both endpoints; no use of `run_in_executor(None, ...)`

## 7. Compose Cloud-Only Guardrails (C-9)

- [x] 7.1 Add `ENVIRONMENT: dev` to every service's environment block in `docker-compose.yml`
- [x] 7.2 In `shared/config.py`, add a validator: when `environment != "dev"`, reject any URL whose parsed hostname is in `{localhost, 127.0.0.1, 0.0.0.0, postgres, redis}`, with a clear `ValueError`
- [x] 7.3 Create `docker-compose.prod.yml` override: no local postgres/redis services, all URLs via `${VAR:?required}` env interpolation, host ports only for gateway (8000) and approval (8004)
- [x] 7.4 Add tests for the non-dev local-host rejection validator (localhost and `postgres:5432` fail in prod; pass in dev; cloud hosts pass in prod)
- [x] 7.5 Verify: `docker compose config` with the prod override fails fast when required env vars are unset

## 8. Verification

- [x] 8.1 Run the full test suite for all affected services (approval, orchestrator, shared) and confirm green
- [x] 8.2 Run `openspec validate fix-critical-audit-findings --strict` and resolve any issues
- [x] 8.3 Smoke-check: orchestrator starts with strong token, `/run` and `/approval-callback` both respect the concurrency limit, semantic cache lookups are non-blocking
