## Why

A systematic full-codebase audit produced two reports (REPORT1_STRUCTURAL_DEBT.md and REPORT2_IMPROVEMENT_GAPS.md) identifying 40+ concrete issues across all eight service folders. Three of these are active bugs in production (episodic memory chunks silently deliver empty strings to the LLM, the concurrency semaphore has a TOCTOU race, and the approval CSRF guard fail-opens on Redis errors); the rest are structural debt and missing production basics that make the project harder to maintain, scale, and present to technical reviewers.

## What Changes

- **Bug fixes** – fix episodic chunk key mismatch (`"text"` → `"content"` in retriever.py); fix semaphore TOCTOU race in orchestrator concurrency gate; fix CSRF verify fail-open in approval/queue.py
- **Dead code removal** – remove dead gateway `/v1/approval-callback` route (nothing calls it, it is a publicly-reachable approval-forge vector); remove asyncpg from action service requirements; remove committed ChromaDB binaries from git; remove redundant `typing-extensions` dep; remove stale `_BYPASS_PATHS` entries; remove `inspect.isawaitable` shim in approval/main.py
- **Duplicate logic consolidation** – extract `_mutate_ticket()` helper (three near-identical ticket handlers); consolidate `AuditLogRequest` into `shared/models/audit.py` (used by 4 files); extract shared ingest loop in `_run_ingest` and `ingest_knowledge.py`; make `seed_data.py` read from the JSON master instead of a hardcoded list
- **Inconsistent patterns normalisation** – unify HTTP client construction across all services to use `create_async_http_client()`; normalise chunk dict keys for episodic memory; unify exception attribute access (`exc.message` vs `str(exc)`)
- **Security hardening** – make audit history endpoints authenticated (`verify_service_token`); make CSRF verification fail-closed; add startup validator for default `hitl_service_token`; remove hardcoded dev API key from Streamlit UI default
- **Missing production basics** – restore/create `README.md` at repo root; fix `render.yaml` to include all 5 missing services; add `APPROVAL_URL` to render.yaml frontend env vars; fix `prune_stale_checkpoints` to also prune `checkpoint_writes`; fix knowledge `requirements.txt` (swap dead deps for the real ones)
- **Over-engineering removal** – delete the ChromaDB semantic query cache (correctness bug + wrong tool for 55-doc corpus); replace Redis distributed lock on a local JSON file with a process-local `threading.Lock`; simplify `_run_ingest` loop

## Capabilities

### New Capabilities

- `audit-contract`: Move `AuditLogRequest` to `shared/models/audit.py` as the single cross-service contract; all three producers (`audit_client.py`, `decider.py`, `memory_writer.py`) and the audit service use the shared model
- `readme-and-onboarding`: A complete `README.md` at repo root (quickstart, architecture link, CI badge, demo instructions) replacing the deleted file

### Modified Capabilities

- `approval-security-guardrail`: CSRF verification changed from fail-open to fail-closed; audit history endpoints gain authentication; `hitl_service_token` default triggers a startup validation error in non-dev environments
- `knowledge-cache`: Semantic query cache (ChromaDB-based, unbounded, correctness-buggy) removed entirely; the spec is updated to reflect no-cache as the correct approach for this corpus size
- `action-dispatch`: Ticket handler consolidated from 3 near-identical mutation functions to a shared `_mutate_ticket` helper; Redis distributed lock replaced with `threading.Lock`; `asyncpg` dependency removed from the action service image
- `shared-http-client-factory`: All services normalised to use `create_async_http_client()`; action service lifespan fixed; orchestrator inline client in `_fetch_session_messages` fixed
- `orchestrator-concurrency-control`: Semaphore TOCTOU race fixed using `asyncio.wait_for`; concurrency limit and worker count made env-configurable

## Impact

- **`shared/models/`** – new `audit.py`; existing `action.py`, `knowledge.py` unchanged
- **`services/action/`** – `main.py` (HTTP client), `handlers/ticket_handler.py` (consolidation + lock), `requirements.txt` (remove asyncpg + Redis lock dep)
- **`services/approval/`** – `queue.py` (CSRF fail-closed), `main.py` (remove isawaitable shim)
- **`services/audit/`** – `main.py` (auth on history endpoints, use shared model), `audit_store.py` (accept model directly)
- **`services/gateway/`** – `main.py` (delete dead callback route + bypass path cleanup)
- **`services/knowledge/`** – `retriever.py` (delete semantic cache), `requirements.txt` (fix deps)
- **`services/orchestrator/`** – `main.py` (fix semaphore, fix inline HTTP client, fix checkpoint pruning), `graph/nodes/retriever.py` (fix chunk key)
- **`scripts/`** – `seed_data.py` (read from JSON master), `ingest_knowledge.py` (thin HTTP wrapper)
- **`data/`** – `data/chroma/` removed from git; `.gitignore` updated
- **`render.yaml`** – 5 missing services added, `APPROVAL_URL` set for frontend
- **`README.md`** – restored at repo root
- No public API surface changes; no database schema changes
