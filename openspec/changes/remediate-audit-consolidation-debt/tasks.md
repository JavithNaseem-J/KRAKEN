## 1. Stage 1 — Consolidated runtime fix

- [x] 1.1 In `src/api/routes.py` lifespan, enter each sub-app's `router.lifespan_context(app)` in order (knowledge, memory, audit, action, approval, orchestrator) with per-app try/except logging `<name>.degraded`; store contexts on `app.state` and exit them in reverse on shutdown
- [x] 1.2 Generalize `src/utils/http_client.py`: add `internal_request(method, url, ...)` with the in-process ASGI short-circuit for GET/POST/DELETE; keep `post_with_retry` as a wrapper; change tenacity retry to transport errors + 5xx only (no 4xx retries)
- [x] 1.3 Delete `_get_in_process_transport` mapping from `src/api/routes.py` and route `_proxy`/`stream_generator` through `get_in_process_app_for_url`
- [x] 1.4 Convert raw internal calls to the shared helper: `src/utils/audit_client.py` (`fire_audit_log`), `src/agent/nodes/retriever.py` episodic-memory search, `src/api/orchestrator.py` `_fetch_session_messages`, `src/api/approval.py` `_notify_orchestrator_callback`
- [x] 1.5 Add gateway proxy routes `GET /approve/{approval_id}/details` and `POST /approve/{approval_id}/decision` in `src/api/routes.py` forwarding to the in-process approval app
- [x] 1.6 Fix `src/api/routes.py` `/v1/run/stream`: import `ValidationError` at module top so invalid payloads return 422 instead of NameError
- [x] 1.7 Remove the unreachable `wait_approval` branch from `src/agent/router.py`
- [x] 1.8 Remove the OpenTelemetry import block and instrumentation section from `src/api/orchestrator.py`
- [x] 1.9 Extract `_initial_state`, `_persist_pending_approval`, `_clear_stale_interrupt` helpers in `src/api/orchestrator.py` and use them from both `/run` and `/run/stream`
- [x] 1.10 Verify standalone boot: `python main.py` starts, `/health` and `/ready` return 200 with subsystems initialized (no AttributeError in logs)

## 2. Stage 2 — Integration test gate

- [x] 2.1 Create `tests/integration/test_consolidated_flow.py` fixture: `TestClient(src.api.routes.app)` with real lifespan, fakeredis, in-memory Postgres fallbacks, LLM mocked at `get_llm`
- [x] 2.2 Add test: `/health` returns ok and `/ready` returns 200 naming all subsystems ready
- [x] 2.3 Add test: `POST /v1/run` happy path returns a `QueryResponse` (mocked SAFE decision)
- [x] 2.4 Add test: HITL approve path — forced CRITICAL decision → `pending_approval` → gateway `GET /approve/{id}/details` returns payload + CSRF → `POST /approve/{id}/decision` resumes graph → final response contains action result
- [x] 2.5 Add test: HITL reject path — decision `reject` cancels the action and the action handler is never invoked
- [x] 2.6 Add test: `POST /v1/run/stream` emits SSE events terminating in a `done` event carrying the response payload
- [x] 2.7 Add test: invalid payload to `/v1/run/stream` returns 422
- [x] 2.8 Update `tests/conftest.py` docstring to describe the `src` layout; confirm `pytest tests/` collects without import errors

## 3. Stage 3 — Duplicate and dead-code removal

- [x] 3.1 Grep the repo for every module scheduled for deletion; record all importers (expected: only the three pinned tests)
- [x] 3.2 Delete `src/utils/action/` subtree (duplicate of `src/tools/*` + `src/safety/*`)
- [x] 3.3 Delete `src/tools/ticket_handler.py`, `src/tools/write_handler.py`, `src/tools/path_validator.py`; trim `src/tools/__init__.py` to `ticket`, `write_tool`
- [x] 3.4 Delete `src/agent/executor.py` and `src/agent/memory.py` (duplicates of `src/agent/nodes/*`)
- [x] 3.5 Delete `src/api/middleware/rate_limit.py`, `src/api/middleware/rate_limiter.py`, `src/utils/middleware/prompt_guard.py`; keep `src/utils/middleware/rate_limit.py` and `src/api/middleware/prompt_guard.py` as canonical
- [x] 3.6 Delete dead stubs: `src/tools/calculator.py`, `src/tools/search.py`, `src/models/embeddings.py`, `src/prompts/` (both files), `src/api/schemas.py`, `src/utils/helpers.py`, `src/utils/logger.py`, `src/observability.py`
- [x] 3.7 Repoint tests: `tests/unit/test_ticket_handler.py` → `src.tools.ticket`, `tests/unit/test_path_validator.py` → `src.safety.path_validator`, `tests/unit/test_observability.py` → `src.utils.observability`
- [x] 3.8 Run full verification: `ruff check .`, `pytest tests/unit`, `pytest tests/integration -m integration`, and re-hash `src/` to confirm no duplicate content hashes remain

## 4. Stage 4 — Infra, manifests, scripts, docs

- [x] 4.1 Update `pyproject.toml`: rename project to `kraken`, package discovery for `src*`, add runtime deps `tenacity`, `jinja2`, `langchain-huggingface`; define extras `dev` (pytest, pytest-asyncio, fakeredis, ruff, mypy) and `eval` (ragas, datasets)
- [x] 4.2 Regenerate `uv.lock`; regenerate `requirements.txt` via `uv export --no-dev`; rewrite `requirements-dev.txt` to reference the dev/eval extras
- [x] 4.3 Replace `Dockerfile.standalone` with `Dockerfile`: `python:3.12-slim`, install `requirements.txt`, copy `src/` + `main.py` + `data/`, non-root user, `HEALTHCHECK` on `/health`, `CMD uvicorn src.api.routes:app --port ${PORT:-8000}`
- [x] 4.4 Rewrite `docker-compose.yml`: single `app` service (port 8000, `ENVIRONMENT=dev`, `depends_on` postgres/redis `service_healthy`) + `postgres` (pgvector, init.sql) + `redis`
- [x] 4.5 Rewrite `docker-compose.prod.yml`: infra replicas 0, `${VAR:?}` required cloud URLs (`POSTGRES_URL`, `REDIS_URL`, `GATEWAY_API_KEYS`, `HITL_SERVICE_TOKEN`), only port 8000 published
- [x] 4.6 Update `render.yaml` (dockerfilePath `Dockerfile`, remove hardcoded `kraken-backend-7op1` subdomain, document rewrite target) and confirm `.github/workflows/deploy.yml` composes the rewritten files
- [x] 4.7 Update `.github/workflows/ci.yml`: `astral-sh/setup-uv` + `uv sync --frozen`; run `ruff check`, `mypy src/`, `pytest tests/unit`, `pytest tests/integration -m integration`; frontend `npm run lint` + `npm run build`; docker smoke job builds the single image and checks `/health`
- [x] 4.8 Fix `Makefile`: `type-check` → `mypy src/`, `up/down/status/ingest/seed` targets aligned with single-app compose and ported scripts; remove references to `shared/`/`services/`
- [x] 4.9 Port scripts to `src.*`: `scripts/ingest_knowledge.py` → `src.utils.knowledge.ingest`/`src.utils.cache`/`src.utils.embedder`; `scripts/seed_data.py` → `src.utils.db.tickets`; delete `scripts/start_standalone.py`; retarget `scripts/check_health.py`, `scripts/benchmark.py`, `scripts/run_preprod_qa_gate.py` at the single `:8000` app
- [x] 4.10 Port `tests/evals/eval_harness.py` and `tests/evals/test_rag_evals.py` to the consolidated endpoints (`http://localhost:8000` via gateway)
- [x] 4.11 Rewrite `README.md` quickstart (env setup, `uv sync`, `docker compose up`, `python main.py`) and service-topology section for the consolidated architecture; update `docs/architecture.md` and `docs/deployment.md` to match
- [x] 4.12 Set frontend `VITE_APPROVAL_URL` default to the gateway URL in `frontend-react/.env.example` and delete `frontend-react/tsconfig.tsbuildinfo` from tracking

## 5. Stage 5 — Commit the migration

- [x] 5.1 Run the full gate locally: `ruff check .`, `mypy src/`, `pytest tests/`, frontend `npm run lint && npm run build`, `docker compose up --build -d` + `/health` smoke
- [x] 5.2 Stage all working-tree deletions (`services/`, `shared/`, stale openspec changes), the new `src/` + `main.py`, and all Stage 1-4 modifications; verify `git status` shows no unintended files (no `.env`, no build artifacts)
- [x] 5.3 Commit the migration as one changeset and confirm `git ls-files` contains no `services/` or `shared/` paths and HEAD matches disk
