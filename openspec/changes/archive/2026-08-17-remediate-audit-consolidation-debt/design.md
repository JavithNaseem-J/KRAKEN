## Context

The repo is mid-migration: `services/` + `shared/` were deleted from the working tree and re-nested under `src/` (untracked), with `main.py` serving a single gateway app (`src/api/routes.py`). The audit found the consolidation is mechanically incomplete:

- The gateway reaches six in-process sub-apps via `httpx.ASGITransport` (`_get_in_process_transport`, `get_in_process_app_for_url`). ASGITransport never runs sub-app lifespans, so `app.state.queue/store/short_term/long_term/client/retriever/http` is never initialized standalone — every proxied call to approval/audit/memory/knowledge/action 500s with AttributeError, `/ready` is permanently 503, and HITL, audit writes, memory persistence, and RAG retrieval silently fail.
- Four inter-service call sites bypass the in-process short-circuit entirely (raw `client.post` in `audit_client.py`, `nodes/retriever.py` episodic search, `orchestrator.py` session fetch, `approval.py` callback) — they hit dead `localhost:800x` ports.
- ~2,600 lines of hash-identical duplicate modules remain from the move; three unit tests are pinned to the dead copies.
- Dockerfile/compose/render/deploy/Makefile/pyproject/scripts/integration-tests still reference the deleted tree; `requirements.txt` misses hard imports (`tenacity`, `jinja2`).
- The browser-facing approval UI (`/approve/{id}/details`, `/approve/{id}/decision`) has no gateway route, so the frontend cannot reach it in single-port mode.

Constraints: keep the sub-app code shape (FastAPI apps with `Depends(verify_service_token)`) so a future split back to services stays possible; no external service may be required for dev/test (fakeredis + in-memory fallbacks already exist); CI must end green.

## Goals / Non-Goals

**Goals:**
- Standalone mode (`python main.py`) fully functional: RAG retrieval, HITL approval flow, audit trail, short/long-term memory all work in-process with zero TCP listeners between subsystems.
- Exactly one canonical copy of every module; dead stubs deleted; tests pinned to live modules.
- A working install → run → test → deploy path: fixed manifests, single-container Dockerfile + compose, CI running unit + integration tests, README/docs matching reality.
- An integration gate that boots the consolidated app with real lifespans so this failure class is caught permanently.

**Non-Goals:**
- Renaming `src/utils/` or restructuring the `src/` package layout beyond duplicate removal.
- Replacing LangGraph, Qdrant, Redis, or Postgres choices.
- New features (no new actions, endpoints, or UI work).
- Frontend feature work; only the approval base-url default changes (point at gateway).
- Restoring the multi-container deployment as a first-class target (single container becomes the deploy unit).

## Decisions

### D1: Run sub-app lifespans from the gateway lifespan (not mounts, not direct calls)
The gateway lifespan will explicitly enter each sub-app's `router.lifespan_context(app)` in dependency order (knowledge → memory → audit → action → approval → orchestrator) and exit them in reverse on shutdown, with per-app `try/except` logging degraded mode instead of failing boot (matching the existing degraded-mode conventions).

- **Why not `app.mount`:** mounting changes external URL paths and CORS/preflight semantics, breaking the frontend contract and rate-limit path prefixes.
- **Why not direct function calls (drop HTTP entirely):** bypasses `verify_service_token`, middleware, and pydantic request validation that tests and the security model rely on; much larger refactor with higher regression risk.
- **Trade-off accepted:** internal calls still traverse ASGI/HTTP machinery in-process; cost is negligible at this traffic and the split-back-to-services option survives.

### D2: One internal-call helper; fix retry semantics
All internal traffic goes through `src/utils/http_client.py`. Generalize to `internal_request(method, url, ...)` supporting GET/POST/DELETE with the in-process transport short-circuit; keep `post_with_retry` as a thin wrapper. Delete the duplicate mapping in `routes.py` (`_get_in_process_transport` uses the shared helper). Convert the four raw-`client.post` sites (audit log, episodic search, session fetch, approval callback) to the helper. Change tenacity retry to fire only on transport errors and 5xx — today `raise_for_status()` makes 4xx retry 3× (e.g. 409 idempotency conflicts retried).

### D3: Gateway exposes approval endpoints for the browser
Add gateway routes proxying `GET /approve/{approval_id}/details` and `POST /approve/{approval_id}/decision` to the approval app via the in-process helper (the HTML form page `GET /approve/{id}` stays optional). Frontend `VITE_APPROVAL_URL` defaults to the gateway URL. This makes single-port deployment sufficient for the full HITL loop.

### D4: Duplicate removal in one atomic step, tests repointed in the same commit
Delete: `src/utils/action/` (subtree), `src/tools/{ticket_handler,write_handler,path_validator}.py`, `src/agent/{executor,memory}.py`, `src/api/middleware/{rate_limit,rate_limiter,prompt_guard}.py`, `src/utils/middleware/prompt_guard.py`, `src/observability.py`, and stubs `src/tools/{calculator,search}.py`, `src/models/embeddings.py`, `src/prompts/`, `src/api/schemas.py`, `src/utils/{helpers,logger}.py`. Trim `src/tools/__init__.py` to live modules. Canonical winners: `src/tools/{ticket,write_tool}.py`, `src/safety/{path_validator,backup}.py`, `src/utils/middleware/{rate_limit,trace_id}.py`, `src/api/middleware/prompt_guard.py`, `src/utils/observability.py`, `src/agent/nodes/*`. Repoint `test_ticket_handler.py`, `test_path_validator.py`, `test_observability.py` in the same commit; verify with repo-wide grep + full pytest + ruff.

### D5: Dependency manifests — pyproject is truth, uv.lock pins, requirements.txt generated
`pyproject.toml` becomes the real project (`kraken`, packages `src*`) with `dependencies` (add `tenacity`, `jinja2`, `langchain-huggingface`) and extras `dev` (pytest, fakeredis, ruff, mypy) and `eval` (ragas, datasets). Regenerate `uv.lock`; CI uses `astral-sh/setup-uv` + `uv sync --frozen`. `requirements.txt` is regenerated via `uv export --no-dev` and kept only for the Docker build. Remove pytest/ragas/datasets from runtime requirements.

### D6: Single-container deployment unit
New `Dockerfile.standalone`: `python:3.12-slim`, install from `requirements.txt`, copy `src/` + `main.py` + `data/`, non-root user, `HEALTHCHECK` on `/health`, `CMD uvicorn src.api.routes:app --host 0.0.0.0 --port ${PORT:-8000}`. `docker-compose.yml`: `app` (8000) + `postgres` (pgvector, init.sql) + `redis`, `depends_on: service_healthy`, `ENVIRONMENT=dev`. `docker-compose.prod.yml`: infra replicas 0, `${VAR:?}` required cloud URLs, only 8000 published. `render.yaml`: one backend web service + static frontend; remove the hardcoded `kraken-backend-7op1` subdomain from the rewrite (document the post-deploy value). Delete `scripts/start_standalone.py`; `deploy.yml` unchanged in shape (it composes the same files).

### D7: Integration gate design
`tests/integration/test_consolidated_flow.py` (marker `integration`, included in CI): `TestClient(gateway_app)` with real lifespan; LLM mocked at the `get_llm` boundary; fakeredis for rate limiter + approval queue; in-memory Postgres fallbacks. Cases: `/health` + `/ready` 200; `/v1/run` happy path returns `QueryResponse`; HITL e2e — forced CRITICAL decision → `pending_approval` → gateway `/approve/{id}/details` returns CSRF → decision POST → graph resumes → final answer; `/v1/run/stream` emits `done` with response. CI gains: integration job, `mypy src/`, frontend `npm run lint`; docker smoke job builds the new single image.

### D8: Small defect fixes carried along
`routes.py` `/v1/run/stream`: import `ValidationError` at module top (fixes NameError → 422). `src/agent/router.py`: delete the unreachable `wait_approval` branch. `orchestrator.py`: remove the stale OpenTelemetry import/instrumentation block (lean-agent-runtime spec). Extract `_initial_state`, `_persist_pending_approval`, `_clear_stale_interrupt` in orchestrator to kill the run/run_stream copy-paste blocks.

## Risks / Trade-offs

- [Sub-app lifespan failure blocks gateway boot] → wrap each lifespan entry in try/except, log `degraded`, continue; `/ready` reports the degraded subsystem (matches existing degraded-mode patterns).
- [Duplicate deletion breaks an import nobody knew about] → repo-wide grep for every deleted module path, full pytest + ruff + frontend build before committing; tests repointed in the same commit.
- [Integration tests flaky on real Redis/LLM] → fakeredis (already a dev dep) + ApprovalQueue's in-memory fallback; LLM mocked at `get_llm`; no network in the gate.
- [Breaking change for existing multi-container deployers] → announced in README/deployment docs; compose service names and env var names kept stable where possible; prod overlay semantics preserved.
- [`uv` unavailable in some environments] → CI uses the official setup-uv action; Docker build uses the exported `requirements.txt`, so uv is never needed at image build time.
- [In-process ASGI adds per-request overhead vs direct calls] → accepted; measured cost is negligible compared to LLM latency, and it preserves auth/middleware parity (D1).

## Migration Plan

1. **Stage 1 — Runtime fix** (D1, D2, D3, D8): gateway lifespan boots sub-apps; internal calls unified; approval proxy routes added; defect fixes.
2. **Stage 2 — Integration gate** (D7): tests written against Stage 1, added to CI. Gate must pass before any deletion.
3. **Stage 3 — Duplicate removal** (D4): deletions + test repoints, verified by Stage 2 gate + full suite.
4. **Stage 4 — Infra/manifest/docs** (D5, D6): Dockerfile, compose, render/deploy, Makefile, pyproject/requirements/uv.lock, scripts ported to `src.*`, README/docs rewritten, OTEL block removed.
5. **Stage 5 — Commit the migration**: stage all working-tree deletions + `src/` additions as one changeset so HEAD matches disk.

Rollback: each stage is an independent commit; revert in reverse stage order. Stage 3 rollback restores duplicates without affecting runtime behavior.

## Open Questions

- Should the gateway also proxy the HTML approval page (`GET /approve/{id}`) for single-port browser access, or is the JSON inline card (already proxied via D3) sufficient? Default: JSON endpoints only; add HTML proxy later if the standalone page is needed.
- Keep `Dockerfile.standalone` as the filename (render.yaml references it) or rename to `Dockerfile`? Default: rename to `Dockerfile` and update render.yaml in the same commit.
