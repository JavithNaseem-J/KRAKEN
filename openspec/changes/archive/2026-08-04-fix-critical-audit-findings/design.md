# Design: fix-critical-audit-findings

## Context

The 2026-08-04 staff-engineer audit (`technical_audit.md`) identified 9 critical defects. This change remediates 7 of them (C-1 through C-6, C-9). C-7 (hybrid search) and C-8 (Ragas eval) are handled by the in-progress change `hybrid-search-rerank-postgres-tickets-ragas` and are out of scope here.

Current state highlights:

- `.env` line 7 contains a live Groq `LLM_API_KEY`; `.env` is in `.gitignore` but the key is in git history.
- `shared/config.py:96` validates `hitl_service_token` only when `environment != "dev"`; `.env` never sets `ENVIRONMENT`, so the guard is a no-op in practice.
- `services/approval/queue.py:113-126` verifies the CSRF token with `redis.get()` but never deletes it; the `akea:csrf:{approval_id}` key lives until TTL (up to 15 min), leaving a replay window. `resolve()` at line 96 already uses the correct `getdel()` pattern.
- `shared/cache.py` `SemanticCache` uses the synchronous `QdrantClient`; `collection_exists()` runs during the orchestrator's async `lifespan()` (main.py:201), and `get()`/`put()` block the event loop per lookup.
- `services/orchestrator/graph/nodes/retriever.py:61` and `executor.py:17` call `time.sleep()` inside retry loops while running on a bounded `ThreadPoolExecutor(max_workers=4)`, starving the pool during partial outages.
- `services/orchestrator/main.py:461` resumes paused graphs via `run_in_executor(None, ...)` — Python's unbounded default executor — with no semaphore, bypassing the `orchestrator_max_concurrency` load shedding that `/run` enforces (lines 322-341).
- `docker-compose.yml` provisions local Postgres/Redis with hardcoded credentials, sets no `ENVIRONMENT`, and `.env` points `POSTGRES_URL` at the Docker-internal host — a prod deploy can silently write to an ephemeral local DB.

Constraints: cloud-only production model (Supabase/Neon + Upstash + Qdrant Cloud); semantic cache SLA <30ms; minimal intrusion into existing code; follow existing patterns (fail-closed, structlog, settings via `shared/config.py`).

## Goals / Non-Goals

**Goals:**
- Eliminate all committed/live secrets from the repo and prevent recurrence via pre-commit scanning.
- Make weak/default HITL token rejection unconditional (environment-independent).
- Close the CSRF replay window with atomic consume-on-verify.
- Remove all blocking synchronous I/O from async code paths in the orchestrator (semantic cache) and eliminate retry-induced thread-pool starvation.
- Bring `/approval-callback` under the same bounded executor + semaphore load-shedding as `/run`.
- Make accidental local-DB usage in non-dev environments impossible (fail-fast at startup) and provide a prod compose override with no hardcoded defaults.

**Non-Goals:**
- Hybrid/sparse retrieval and Ragas evaluation (covered by `hybrid-search-rerank-postgres-tickets-ragas`).
- Section-2 "Improvement" findings (per-service tokens, rate limiting, `top_k` validation, Langfuse handler, etc.) — separate change(s).
- Purging the leaked key from git history (force-rewrite); rotation + prevention is the chosen remediation.
- Changing the LangGraph node sync-execution model overall (nodes stay sync functions on the worker pool; only the retry-blocking behavior is fixed).

## Decisions

### D1 (C-1): Rotate key, scrub `.env`, add `gitleaks` pre-commit hook — no history rewrite
- Rotate the Groq key immediately (operator action, out-of-band). Replace the value in `.env` with a placeholder and add/refresh `.env.example` documenting that real keys come only from the environment / secrets manager.
- Add a `.pre-commit-config.yaml` with `gitleaks` to block future secret commits.
- **Alternatives considered:** (a) Rewriting git history with `git filter-repo` — rejected: destructive for all clones, and rotation already invalidates the leaked credential; (b) `detect-secrets` instead of `gitleaks` — `gitleaks` chosen for zero-config baseline scanning, either is acceptable at implementation time.

### D2 (C-2): Entropy-based, unconditional token validation
- Replace the environment-conditional check in `validate_production_secrets` with an unconditional rule: raise `ValueError` if `hitl_service_token == "change-me-in-production"` OR `len(hitl_service_token) < 32`, regardless of `ENVIRONMENT` (including unset).
- This is intentionally **BREAKING** for dev: developers must set a unique >= 32-char token (documented in `.env.example` and README). A weak default that is bypassable is worse than a hard failure.
- **Alternatives considered:** (a) Keep the dev bypass — rejected, that is exactly the audit finding; (b) validate entropy via Shannon score — overkill; length + default-value checks are sufficient and deterministic.

### D3 (C-3): Atomic `GETDEL` in `verify_csrf_token()`
- Change `services/approval/queue.py` `verify_csrf_token()` to use `self._redis.getdel(f"akea:csrf:{approval_id}")` — the same atomic pattern already used in `resolve()`. One-shot tokens: successful verification consumes the token; replay within the TTL window finds nothing and fails closed.
- No signature or caller changes needed; existing fail-closed behavior on error/missing token is preserved.

### D4 (C-4): Migrate `SemanticCache` to `AsyncQdrantClient`
- `shared/cache.py`: construct `qdrant_client.AsyncQdrantClient` (URL+key, or `:memory:` for tests), make `_ensure_collection()`, `get()`, and `put()` `async`, and `await` all client calls.
- Orchestrator `lifespan()` awaits collection setup; cache call sites in the orchestrator `await cache.get()` / `cache.put()`.
- The constructor can no longer perform network I/O (async client methods are coroutines); collection setup moves to an explicit `await cache.init()` called during `lifespan()`.
- **Alternatives considered:** (a) Keep the sync client and wrap calls in `run_in_executor` — rejected: adds thread-hopping overhead per cache lookup against the <30ms SLA and the audit explicitly recommends the async client; (b) async throughout including the knowledge service — out of scope, knowledge service already offloads correctly.

### D5 (C-5): Async-retry the graph nodes instead of blocking worker threads
- Convert `retriever_node` and `executor_node` to `async def` using `httpx.AsyncClient` with `tenacity` async retry (`wait_exponential`/linear, stop after 3 attempts), and invoke them via LangGraph's native async support (`graph.ainvoke`) from `/run` and `/approval-callback`.
- This removes both `time.sleep()` blocking and the need for a thread pool for these nodes; the bounded `graph_executor` remains for any residual sync graph work, and the semaphore still bounds concurrency.
- **Alternatives considered:** (a) Size the pool to `max_concurrency × max_retries = 15` — rejected: masks the problem, wastes idle threads, still blocks threads during retries; (b) keep sync nodes and only replace `time.sleep` with a threading-aware backoff — rejected: a blocked thread is a blocked thread regardless of sleep mechanism.

### D6 (C-6): `/approval-callback` uses the same bounded executor + semaphore as `/run`
- In `approval_callback`, acquire `app.state.graph_semaphore` via the same atomic `asyncio.wait_for(..., timeout=0.0)` pattern (HTTP 503 when full), and pass `app.state.graph_executor` to `run_in_executor` (or use `ainvoke` per D5) with release in `finally`.
- Order matters: the Postgres `SELECT FOR UPDATE` idempotency transaction stays as-is and completes **before** semaphore acquisition, so a 503 due to capacity does not mark the approval resolved — the callback can be retried by the caller.
- **Trade-off accepted:** under saturation, callbacks now get 503 instead of unbounded parallelism; the approval service must retry (its existing callback error handling already tolerates non-2xx).

### D7 (C-9): Dev-guard compose, startup DB-host validation, prod override file
- `docker-compose.yml`: add `ENVIRONMENT: dev` to every service; keep local Postgres/Redis for dev only.
- `shared/config.py`: add a startup validator that, when `environment != "dev"`, rejects `postgres_url`/`redis_url`/service URLs pointing at `localhost`, `127.0.0.1`, or the compose service hostnames (`postgres`, `redis`) — fail fast with a clear error.
- New `docker-compose.prod.yml` override: no local Postgres/Redis services, all DB/cache/service URLs injected from env vars with no defaults (`${POSTGRES_URL:?required}` style), only gateway (8000) and approval (8004) ports exposed.
- **Alternatives considered:** (a) Delete local services from compose entirely — rejected: dev convenience is legitimate, the audit only requires a guard; (b) hostname allowlist instead of denylist — denylist of known-local hosts chosen for simplicity; cloud hosts (Supabase/Neon/Upstash) are arbitrary domains.

## Risks / Trade-offs

- [Rotated key still in git history; anyone with an old clone has a dead but sensitive credential] → Rotation invalidates it; `.env.example` + gitleaks prevent recurrence; document the incident in the change notes.
- [Unconditional token validation breaks existing dev setups on next start] → Clear `ValueError` message, updated `.env.example` with a generated-token recipe; breaking change is called out in the proposal.
- [D5 (async nodes) touches the graph invocation path — regression risk in the core request flow] → Covered by existing orchestrator tests plus new tests for retry behavior; `ainvoke`/`invoke` equivalence verified for HITL interrupt/resume flow.
- [503 on `/approval-callback` could strand a paused graph if the approval service does not retry] → Idempotency transaction runs before semaphore acquisition, so the approval stays `pending` and retryable; verify approval service retry behavior during implementation.
- [`getdel` consumes the CSRF token even if a later step fails, forcing form re-render] → Acceptable: one-shot tokens are the security goal; the approval form re-fetches a fresh token on re-render.
- [Prod compose override relies on operators supplying env vars] → `${VAR:?}` syntax fails fast at `docker compose up` with a clear message, which is the intended behavior.

## Migration Plan

1. Rotate the Groq API key in the Groq console; update the secrets manager entry (out-of-band, do first).
2. Land code changes behind normal PR; no data migrations required.
3. Update developer docs: set a unique >= 32-char `HITL_SERVICE_TOKEN` locally; install `pre-commit` hooks (`pre-commit install`).
4. Deploy services; on startup, any env with a weak token or (non-dev) local DB URLs fails fast with an actionable error.
5. Rollback: revert the PR. Note the token validator is breaking-by-design — rollback restores the old bypass, so prefer roll-forward fixes for validator false positives.

## Open Questions

- `gitleaks` vs `detect-secrets` for the pre-commit hook (either satisfies the requirement; decide at implementation).
- Whether the approval service currently retries non-2xx callback responses (affects how visible the new 503 is); to be verified during implementation, with a small retry loop added there only if missing.
