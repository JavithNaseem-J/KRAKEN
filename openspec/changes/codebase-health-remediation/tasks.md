## 1. High-Impact Structural Fixes (Phase 1)

- [x] 1.1 Move `shared/db.py` to `shared/db/pool.py` and create `shared/db/__init__.py` re-exporting `create_pool` and ticket functions
- [x] 1.2 Add missing dependencies to per-service `requirements.txt` (`tenacity` to gateway/approval/action, `qdrant-client` to orchestrator, `langchain-openai` to knowledge/memory)
- [x] 1.3 Move `services/action/audit_client.py` to `shared/audit_client.py` and update imports in orchestrator and action services
- [x] 1.4 Wire `SemanticCache.put()` into orchestrator's `/run` endpoint after successful execution
- [x] 1.5 Fix `services/approval/queue.py:144` `close()` method by replacing missing `contextlib` import with `try/except await self._redis.aclose()`
- [x] 1.6 Single-source `embedding_dim` in `Settings` and update `SemanticCache.init()`, knowledge `ensure_collection()`, and `init.sql`
- [x] 1.7 Rewrite `services/knowledge/loaders/sla_loader.py` to iterate nested `severities` and `action_risk_mapping` in `sla_rules.json`
- [x] 1.8 Update default `hitl_service_token` to `"change-me-in-production"` in `Settings` and remove hardcoded hex key from `scripts/start_standalone.py`

## 2. Medium & Low Priority Debt Cleanups (Phase 2)

- [x] 2.1 Extract CORS middleware kwargs into `shared/cors.py` and call from gateway and approval services
- [x] 2.2 Consolidate rate limiting to Redis-backed limiter and remove leaking in-memory dict
- [x] 2.3 Consolidate DB connection pool creation into `shared/db/`
- [x] 2.4 Delete dead migration directory `migrations/` and `alembic.ini`
- [x] 2.5 Delete duplicate evaluation script `scripts/evaluate_rag.py` and fix `scripts/run_preprod_qa_gate.py` step 5
- [x] 2.6 Extract `_extract_interrupt(snapshot)` helper in orchestrator
- [x] 2.7 Deduplicate ticket payload construction in `services/action/handlers/ticket_handler.py`
- [x] 2.8 Align `QueryResponse` model fields with call site usages
- [x] 2.9 Delete duplicate `.agent/` tool tree (retaining `.opencode/`)
- [x] 2.10 Clean up `shared/embedder.py` (remove unused import/constant, fix `ZeroVectorEmbedder`)
- [x] 2.11 Remove hardcoded Render hostname from `frontend-react/src/services/api.ts`
- [x] 2.12 Clean up unused doc bypass paths, missing `__init__.py` files, and `.env.example` placeholders
- [x] 2.13 Run `ruff check --fix` and resolve remaining lint findings across repository

## 3. Production Readiness & Observability (Phase 3)

- [x] 3.1 Rewrite `.github/workflows/ci.yml` to install full dependency stack, build frontend, and run Docker smoke test
- [x] 3.2 Implement idempotent `ensure_schema()` database bootstrap in audit, memory, and action service lifespans
- [x] 3.3 Add `@pytest.mark.integration` to integration tests and exclude them from default unit test run
- [x] 3.4 Configure ESLint, Prettier, and build scripts in `frontend-react/`
- [x] 3.5 Create `docs/architecture.md` with topology diagram and HITL sequence diagram
- [x] 3.6 Implement cursor/keyset pagination for audit `verify_chain()`
- [x] 3.7 Add Qdrant payload filter to ticket retrieval in knowledge retriever
- [x] 3.8 Add TTL sweep coroutine for in-memory fallback maps
- [x] 3.9 Wire configurable OTLP exporter and Prometheus `/metrics` endpoint in orchestrator and gateway
- [x] 3.10 Add unit tests for orchestrator state-machine (callback approve/reject, reaper, prune checkpoints)
- [x] 3.11 Add README screenshots and live demo links
