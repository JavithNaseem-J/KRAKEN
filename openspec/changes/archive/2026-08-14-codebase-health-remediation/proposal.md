## Why

A comprehensive audit surfaced 31 structural-debt issues (8 High, 14 Medium, 9 Low) and 13 improvement gaps (2 High, 8 Medium, 3 Low) across the KRAKEN codebase. Several High-severity items block basic operations: the `shared/db` module/package collision makes Postgres ticket tables unimportable, per-service Docker images fail to boot due to missing dependencies, the semantic cache is runtime-dead (never written to), and vector dimensions are silently mismatched between config and schema. These are not incremental enhancements — they are defects that prevent the system from functioning as advertised in anything other than standalone mode. Fixing them now is prerequisite to any credible deployment or demo.

## What Changes

### Structural Fixes (High)
- **Resolve `shared/db.py` vs `shared/db/` shadowing** — convert `shared/db.py` to a package with `pool.py` + `__init__.py`; update all import sites.
- **Fix per-service `requirements.txt`** — add `tenacity` to gateway/approval/action, `qdrant-client` to orchestrator, `langchain-openai` to knowledge/memory.
- **Move `audit_client.py` to `shared/`** — eliminate cross-service import that breaks in Docker.
- **Wire `SemanticCache.put()`** — call it after successful `/run` completion so the cache actually caches.
- **Fix approval queue `close()`** — replace broken `contextlib.suppress` (missing import) with `try/except await aclose()`.
- **Unify vector dimension** — expose `embedding_dim` from config/embedder, pass to collection creation and DDL; fail fast on mismatch.
- **Fix SLA loader** — rewrite to match the actual nested JSON shape; produce one chunk per P-level.
- **Fix `hitl_service_token` default** — set to `"change-me-in-production"`, delete hardcoded hex secret from `start_standalone.py`.

### Structural Fixes (Medium)
- **Extract shared CORS config** — `shared/cors.py::cors_middleware_kwargs()` replacing copy-paste in gateway + approval.
- **Consolidate rate limiters** — single Redis-backed implementation; remove leaking in-memory dict.
- **Consolidate DB pool factories** — one `create_async_pool()` and one `create_sync_pool()` in `shared/db/`.
- **Delete dead migration infrastructure** — remove `migrations/` + `alembic.ini`; keep `init.sql` as single DDL source.
- **Parameterize Dockerfiles** — one `services/Dockerfile` with `ARG SERVICE / ARG PORT`.
- **Clean up eval paths** — delete `scripts/evaluate_rag.py`; keep harness + pytest evals.
- **Fix QA gate** — point step 5 at `scripts/benchmark.py` or remove it.
- **Extract `_extract_interrupt()` helper** — deduplicate the snapshot-task extraction block in orchestrator.
- **Deduplicate ticket payload** — build once, branch only on insert mechanism.
- **Fix `QueryResponse` phantom fields** — add `confidence`, `evidence`, `execution_time_sec` to model or remove from call sites.
- **Delete duplicate tool trees** — remove `.agent/` (keep `.opencode/`).
- **Fix embedder hygiene** — delete unused top-level import and `EMBEDDING_DIM`; replace method `lru_cache` with module-level cache.
- **Fix `ZeroVectorEmbedder`** — raise/log error at startup instead of silently returning garbage zero vectors.
- **Remove hardcoded Render hostname** — rely solely on `VITE_API_URL`/`VITE_GATEWAY_URL` env vars.

### Structural Fixes (Low)
- **Remove dead doc bypass paths** — remove `/docs`, `/openapi.json` from auth bypass; fix root endpoint payload.
- **Fix undefined annotations** — add `from typing import Any`; hoist `SemanticCache` import.
- **Fix ruff violations** — `ruff check --fix` + manual fixes for the 63 findings.
- **Remove committed build artifact** — `git rm --cached tsconfig.tsbuildinfo`; add to `.gitignore`.
- **Delete duplicate `_redirects`** — `netlify.toml` wins.
- **Delete unreachable validation branch** — `validate_action_payload` redundant check.
- **Add missing `__init__.py`** — `shared/middleware/` and any other subpackages.
- **Fix `.env.example`** — replace real Supabase hostname; drop unused `GATEWAY_API_KEY`.
- **Delete hand-rolled SAST** — rely on `gitleaks` + `bandit`/`pip-audit` in CI.

### Production Improvements (High)
- **Fix CI workflow** — install real deps, split lint/type/test steps, add Docker build+smoke.
- **Add database bootstrap for cloud** — idempotent `ensure_schema()` in service lifespans.

### Production Improvements (Medium)
- **Mark integration tests** — `@pytest.mark.integration` + skip by default; run in compose-backed CI job.
- **Add frontend build to CI** — `npm run build` + `tsc --noEmit`.
- **Write `docs/architecture.md`** — service topology + HITL sequence diagram.
- **Clean dependency management** — split dev/eval deps; bump langchain/langgraph to 1.x; lock with `uv lock`.
- **Paginate `verify_chain()`** — cursor/keyset pagination for the append-only audit table.
- **Filter ticket scroll** — Qdrant payload filter on `metadata.ticket_id` instead of unfiltered scroll.
- **Cap in-memory fallback maps** — TTL sweep or LRU cap on approval/rate-limiter maps.
- **Wire OpenTelemetry** — OTLP exporter behind env var; add Prometheus `/metrics`.
- **Add orchestrator state-machine tests** — approval callback, reaper, prune_stale_checkpoints.

### Production Improvements (Low)
- **Bypass `/ready` in auth** — add to `_BYPASS_PATHS`.
- **README polish** — screenshots/GIF + live demo link.
- **Add frontend lint config** — ESLint + Prettier.

## Capabilities

### New Capabilities
- `shared-db-package`: Restructures `shared/db` from a conflicting module into a proper Python package with `pool.py`, `tickets.py`, and `__init__.py` re-exports.
- `service-dependency-alignment`: Ensures every per-service `requirements.txt` declares all transitive imports so Docker images boot independently.
- `semantic-cache-activation`: Wires `SemanticCache.put()` into the orchestrator response path so the cache feature actually functions.
- `vector-dimension-unification`: Single-source embedding dimension from config through collection creation, DDL, and search.
- `sla-loader-fix`: Rewrites the SLA knowledge loader to match the actual nested JSON data shape.
- `shared-audit-client`: Moves `audit_client.py` to `shared/` so audit logging works across service boundaries in Docker.
- `db-schema-bootstrap`: Adds idempotent `ensure_schema()` for cloud deployments where `init.sql` isn't volume-mounted.
- `ci-pipeline-fix`: Rewrites CI to install real dependencies, split steps, and add Docker smoke tests.
- `observability-upgrade`: Wires OTLP exporter and Prometheus metrics to replace console-only tracing.
- `eval-cleanup`: Consolidates overlapping eval paths and fixes broken QA gate references.
- `frontend-quality-gates`: Adds TypeScript build check, ESLint, and Prettier to the frontend.
- `codebase-hygiene`: Umbrella for all Low-severity cleanups — dead code removal, missing `__init__.py`, ruff fixes, `.gitignore` updates, and documentation gaps.

### Modified Capabilities
- `structural-debt-and-defect-fixes`: Extends with approval queue `close()` fix, `hitl_service_token` default fix, `QueryResponse` phantom fields, `ZeroVectorEmbedder` fail-loud, embedder import hygiene, and extracted helpers.
- `docker-standardization`: Extends with parameterized single `Dockerfile` replacing 7 copies.
- `ci-workflow`: Extends with real dependency installation, frontend build step, and Docker smoke tests.
- `cloud-deployment`: Extends with `ensure_schema()` database bootstrap and removal of hardcoded Render hostname.
- `knowledge-cache`: Extends with `SemanticCache.put()` wiring and vector dimension alignment.
- `configurable-cors`: Extends with extracted `shared/cors.py` utility.
- `knowledge-loader-consolidation`: Extends with SLA loader data-shape fix.
- `pre-production-qa`: Extends with fixed QA gate step 5 reference.

## Impact

- **`shared/`**: Major restructuring — `db.py` becomes `db/` package; new `cors.py`, `audit_client.py`; embedder fixes; middleware `__init__.py`.
- **`services/*/requirements.txt`**: 6 files updated with missing dependencies.
- **`services/*/Dockerfile`**: 7 files replaced by 1 parameterized template.
- **`services/orchestrator/main.py`**: Cache put wiring, extracted interrupt helper, fixed annotations, pool consolidation.
- **`services/approval/queue.py`**: Fixed `close()` method.
- **`services/knowledge/`**: SLA loader rewrite, retriever ticket filter, dimension alignment.
- **`services/action/`**: `audit_client.py` moved out, ticket handler deduplication.
- **`services/audit/`**: `verify_chain()` pagination.
- **`.github/workflows/ci.yml`**: Complete rewrite.
- **`docker-compose.yml` / `docker-compose.prod.yml`**: Build args for parameterized Dockerfile.
- **`frontend-react/`**: Remove hardcoded hostname, add lint config, add to CI, gitignore build artifacts.
- **`scripts/`**: Delete `evaluate_rag.py`, `run_security_audit.py`; fix `run_preprod_qa_gate.py`.
- **`migrations/` + `alembic.ini`**: Deleted.
- **`.agent/`**: Deleted (duplicate of `.opencode/`).
- **`shared/models/agent.py`**: Add or remove phantom fields on `QueryResponse`.
- **`shared/config.py`**: New `embedding_dim` setting; fixed `hitl_service_token` default.
- **`docs/architecture.md`**: New file with service diagram and HITL sequence.
- **`README.md`**: Screenshots and live demo link.
- **Breaking changes**: None — all fixes correct currently-broken behavior.
