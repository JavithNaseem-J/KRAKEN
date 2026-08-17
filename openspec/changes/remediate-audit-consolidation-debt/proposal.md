## Why

The 2026-08-17 full-codebase audit (28 debt issues, 11 high) found that the microservice→monolith migration left the repo in a broken intermediate state: ~2,600 lines of hash-identical duplicate modules, a single-process runtime whose sub-app state is never initialized (HITL, audit, memory, and RAG silently fail via `httpx.ASGITransport` calls to apps whose lifespans never run), a build/deploy/CI surface that references the deleted `services/`/`shared/` tree, and a dependency manifest missing hard runtime imports (`tenacity`, `jinja2`). Nothing installs, deploys, or passes `make test` today, and the migration itself is uncommitted (111 deletions + untracked `src/`).

## What Changes

- **Fix the consolidated runtime**: initialize every subsystem's state (approval queue, audit store, memory stores, knowledge retriever, orchestrator graph, shared HTTP client) when the single gateway app boots; unify all internal calls through one helper so no call depends on a TCP listener; fix the `ValidationError` NameError in `/v1/run/stream`; remove the dead `wait_approval` router branch.
- **BREAKING** Remove ~2,600 lines of duplicate modules: `src/utils/action/` (entire subtree), `src/tools/{ticket_handler,write_handler,path_validator}.py`, `src/agent/{executor,memory}.py`, duplicate middleware (`src/api/middleware/{rate_limit,rate_limiter,prompt_guard}.py`, `src/utils/middleware/prompt_guard.py`), `src/observability.py`, and dead stubs (`src/tools/{calculator,search}.py`, `src/models/embeddings.py`, `src/prompts/`, `src/api/schemas.py`, `src/utils/{helpers,logger}.py`); repoint the three tests pinned to duplicate copies.
- **Re-anchor build/deploy to the monolith**: replace `Dockerfile.standalone` with a single-app image (`src/` + `main.py`), rewrite `docker-compose.yml`/`docker-compose.prod.yml` as app + postgres + redis, update `render.yaml`/`deploy.yml`, and delete `scripts/start_standalone.py`.
- **Fix dependency manifests**: add missing runtime deps (`tenacity`, `jinja2`, `langchain-huggingface`), move test/eval deps to dev/eval groups, make `pyproject.toml` describe the real app, and adopt `uv.lock` as source of truth.
- **Port stale scripts/tests to `src.*`**: `scripts/{ingest_knowledge,seed_data,check_health,benchmark}.py`, `tests/integration/test_e2e_flow.py`, eval harness endpoints; fix `Makefile` and `conftest.py`.
- **Add an integration test gate**: boot the consolidated app with real lifespans and exercise the full HITL flow (run → interrupt → approve → resume); run it in CI.
- **Update documentation**: rewrite `README.md` and `docs/architecture.md` for the consolidated architecture; remove the stale OpenTelemetry block from the orchestrator per the lean-runtime spec.
- Commit the completed migration as one changeset so HEAD matches disk.

## Capabilities

### New Capabilities

- `consolidated-runtime-bootstrap`: Single-process startup MUST initialize all subsystem state and serve HITL, audit, memory, and retrieval without requiring per-service TCP listeners.
- `integration-test-gate`: An integration suite that boots the consolidated application with real lifespans and verifies the end-to-end HITL flow, wired into CI.

### Modified Capabilities

- `standard-agent-structure`: Adds a requirement that every module exists in exactly one canonical location and package `__init__` files do not import dead duplicates.
- `lean-agent-runtime`: Adds a requirement that no legacy microservice scaffolding remains in tracked content (OTEL block removed, `services/`/`shared/` deletions committed, scripts/tests import only `src.*`).
- `docker-standardization`: Replaces the per-service Dockerfile requirement with a single-application image requirement and updates the production compose override for the single-app topology.
- `ci-pipeline-fix`: CI installs from the consolidated manifest, runs unit + integration tests and mypy over `src/`, and smoke-checks the single-app image.

## Impact

- **Code**: `src/api/routes.py`, `src/api/orchestrator.py`, `src/utils/http_client.py`, `src/utils/audit_client.py`, `src/agent/nodes/retriever.py`, `src/agent/router.py`, `src/api/approval.py`; deletion of ~20 duplicate/dead files under `src/`.
- **Infra**: `Dockerfile.standalone`, `docker-compose.yml`, `docker-compose.prod.yml`, `render.yaml`, `.github/workflows/{ci,deploy}.yml`, `Makefile`, `pyproject.toml`, `requirements*.txt`, `uv.lock`.
- **Tests**: `tests/integration/` rewritten; `tests/unit/test_ticket_handler.py`, `test_path_validator.py`, `test_observability.py` repointed; new integration gate in CI.
- **Docs**: `README.md`, `docs/architecture.md`, `docs/deployment.md`.
- **Behavior**: standalone mode gains working HITL/audit/memory/RAG; external multi-container deployment is replaced by a single-container deployment (breaking for anyone deploying the old 7-service topology).
