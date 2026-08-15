## Context

KRAKEN is a multi-service AI agent platform (gateway → orchestrator → knowledge/action/approval/memory/audit) that can run as a standalone monolith (`Dockerfile.standalone`) or as 7 independent Docker microservices. A comprehensive audit surfaced 31 structural-debt issues and 13 improvement gaps. Many High-severity items cause silent failures: Docker images won't boot, the semantic cache never stores anything, vector dimensions are silently mismatched, and the `shared/db` Python module shadows its own package directory. The existing 35 specs cover the intended behavior but several features are broken in practice.

### Current State of Key Components
- **`shared/db.py`** (63 LOC): asyncpg pool factory. Coexists with `shared/db/tickets.py` — Python resolves `shared.db` to the module, making `shared.db.tickets` unimportable.
- **`shared/cache.py`** (138 LOC): `SemanticCache` with working `get()` and `put()` methods, but `put()` is never called anywhere.
- **`shared/embedder.py`** (108 LOC): `BGEEmbedder` with cloud/local/zero-vector paths. Top-level `langchain_huggingface` import forces the dep on all importers; `ZeroVectorEmbedder` silently returns garbage.
- **`shared/config.py`** (223 LOC): Pydantic Settings with `hitl_service_token` defaulting to a real 64-char hex secret while the validator checks for `"change-me-in-production"` — a value that is never the default.
- **Per-service `requirements.txt`**: Missing `tenacity`, `qdrant-client`, `langchain-openai` across multiple services.
- **`.github/workflows/ci.yml`**: Installs only ruff/mypy/pytest/httpx — test imports fail because FastAPI/langchain/etc. are never installed.

## Goals / Non-Goals

**Goals:**
- Make all 7 microservice Docker images boot successfully with correct dependencies
- Make `shared.db.tickets` importable (resolve module/package shadowing)
- Make `SemanticCache` functional end-to-end (put + get)
- Unify vector dimension from config through DDL and collection creation
- Fix all High-severity runtime errors (approval `close()`, SLA loader, token default)
- Make CI pass with real dependencies and meaningful test results
- Eliminate cross-service import boundaries that break in Docker
- Remove dead code, duplicate structures, and phantom model fields
- Add database bootstrap for cloud deployments

**Non-Goals:**
- Rewriting the LangGraph agent graph or orchestrator state machine
- Migrating from Qdrant to another vector DB
- Adding new features (e.g., multi-tenant isolation, new action types)
- Changing the frontend framework or doing major UI work
- Full observability platform setup (just wire OTLP exporter, not deploy Jaeger/Grafana)
- Performance optimization beyond the specific `verify_chain()` and `scroll()` fixes

## Decisions

### D1: `shared/db` Package Restructure
**Decision**: Move `shared/db.py` → `shared/db/pool.py`, keep `shared/db/tickets.py`, add `shared/db/__init__.py` re-exporting `create_pool` and ticket helpers.

**Rationale**: This is the minimal change — the 4 import sites (`from shared.db import create_pool`) continue to work via the `__init__.py` re-export. No code changes needed at call sites beyond the module move.

**Alternative considered**: Rename `shared/db/` to `shared/db_tickets/` — rejected because it forces changes at more import sites and the package name is less intuitive.

### D2: Dependency Alignment via Per-Service `requirements.txt`
**Decision**: Add missing dependencies directly to each service's `requirements.txt` rather than creating a shared `pyproject.toml` extras system.

**Rationale**: The project already uses per-service requirements files consumed by per-service Dockerfiles. Adding a centralized dependency manager would be a larger refactor. Simply declaring what each service actually imports is the fastest path to bootable images.

**Alternative considered**: Declare shared deps in `pyproject.toml` `[project.optional-dependencies]` — valid but requires changing all Dockerfiles' pip install lines; deferred to a future change.

### D3: `SemanticCache.put()` Wiring
**Decision**: Call `cache.put(query_vector, body.message, response_dict)` in the orchestrator's `/run` endpoint after successful graph execution, before returning the response.

**Rationale**: The cache infrastructure is already complete (`put()` method exists and works). The only missing piece is the call site. Placing it after successful completion ensures only valid responses are cached.

### D4: Embedding Dimension Unification
**Decision**: Add `embedding_dim: int` to `Settings` with a default derived from the model name (1536 for `text-embedding-3-small`, 384 for `bge-small-en`). Pass this value to `SemanticCache.init()`, `ensure_collection()`, and the DDL `init.sql`.

**Rationale**: Hardcoding 384 in 5 places while the default provider produces 1536-dim vectors is a silent data corruption bug. Single-sourcing from config prevents mismatch.

### D5: Audit Client Relocation
**Decision**: Move `services/action/audit_client.py` → `shared/audit_client.py`. Update imports in both orchestrator and action service.

**Rationale**: The orchestrator already imports from `services.action.audit_client` which only works in standalone mode. Moving to `shared/` makes it available to all services in Docker.

### D6: Single Parameterized Dockerfile
**Decision**: Replace 7 near-identical Dockerfiles with `services/Dockerfile` using `ARG SERVICE` and `ARG PORT`. Update `docker-compose.yml` and `docker-compose.prod.yml` to pass build args.

**Rationale**: The 7 Dockerfiles differ only in service path and port number. A single template eliminates the maintenance burden of synchronized changes across 7 files.

### D7: CI Pipeline Rewrite
**Decision**: Install the full dependency set (`requirements.txt` + `requirements-dev.txt` + per-service reqs) in CI. Split into separate lint, type-check, test, and Docker smoke steps. Add `npm run build` for the frontend.

**Rationale**: Current CI installs only 4 packages and every test fails on import. A CI pipeline that can never pass provides no value.

### D8: Delete Dead Infrastructure
**Decision**: Delete `migrations/` + `alembic.ini` (keep `init.sql` as single DDL source). Delete `scripts/evaluate_rag.py` and `scripts/run_security_audit.py`. Delete `.agent/` (duplicate of `.opencode/`).

**Rationale**: Dead code creates confusion and maintenance overhead. Alembic is not wired into any startup or CI path. The eval script references a non-existent dataset. The security scanner has a self-defeating allowlist. `.agent/` is byte-identical to `.opencode/`.

### D9: SLA Loader Rewrite
**Decision**: Rewrite `_rule_to_text()` and `load_sla_chunks()` to iterate the actual nested JSON structure (`severities.P1..P4` + `action_risk_mapping`) instead of expecting flat records.

**Rationale**: The current loader produces one garbage chunk because it treats the root object as a flat rule record. The fix must match the shipped data shape.

### D10: Database Schema Bootstrap
**Decision**: Add an idempotent `ensure_schema()` function that runs `init.sql` DDL statements during service lifespan startup for audit/memory/action services when Postgres is configured.

**Rationale**: `init.sql` only runs via Docker entrypoint volume mount in local dev. Cloud deployments (Render/Supabase) never execute it, leaving audit/memory tables missing.

### D11: `ZeroVectorEmbedder` Fail-Loud
**Decision**: Log an error at startup when `ZeroVectorEmbedder` is activated and set a flag that disables retrieval features (cache lookup, knowledge search return empty). Do not silently produce zero vectors that corrupt search results.

**Rationale**: Zero vectors have undefined cosine similarity behavior — they return arbitrary "matches" that degrade retrieval to garbage. Failing visibly is strictly better than silently degrading.

### D12: In-Memory Fallback Caps
**Decision**: Add TTL-based expiry to in-memory maps (`_IN_MEMORY_APPROVAL_MAP`, CSRF map, rate-limiter IP dict) using a periodic sweep coroutine. Document that fallbacks are dev-only.

**Rationale**: These maps grow without bound in long-running processes. A TTL sweep prevents OOM in development while Redis handles production.

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| `shared/db` rename breaks undiscovered import sites | Medium | Grep for all `from shared.db` and `import shared.db` patterns before moving; `__init__.py` re-export preserves backward compat |
| Adding deps to requirements.txt introduces version conflicts | Low | Pin to ranges compatible with existing `requirements.txt`; CI will catch conflicts |
| `cache.put()` in hot path adds latency | Low | `put()` is already async and fail-open; wrap in `asyncio.create_task()` to not block response |
| Deleting migrations/ removes future Alembic option | Low | `init.sql` remains as DDL source; Alembic can be re-added if needed later |
| Parameterized Dockerfile may not cover service-specific needs | Low | Current Dockerfiles have zero service-specific logic; ARG substitution is sufficient |
| `ensure_schema()` runs DDL on every startup | Low | All statements are idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) |

## Migration Plan

### Deployment Order
1. **Phase 1** (no runtime behavior change): Package restructure (`shared/db`, `__init__.py` files), dead code deletion, dependency alignment, ruff fixes
2. **Phase 2** (runtime fixes): Approval `close()`, SLA loader, token default, `QueryResponse` fields, embedder hygiene
3. **Phase 3** (feature activation): `SemanticCache.put()` wiring, dimension unification, `ensure_schema()`, audit client relocation
4. **Phase 4** (infrastructure): Parameterized Dockerfile, CI rewrite, frontend quality gates, observability wiring

### Rollback Strategy
All changes are backward-compatible. If issues arise:
- Revert the parameterized Dockerfile by restoring the 7 individual files
- `SemanticCache.put()` is gated behind `semantic_cache_enabled` config flag
- `ensure_schema()` is idempotent and skipped when `postgres_url` is empty
