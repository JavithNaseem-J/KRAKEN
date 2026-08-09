## Context

A full-codebase audit of AKEA produced two reports (REPORT1_STRUCTURAL_DEBT.md, REPORT2_IMPROVEMENT_GAPS.md) covering 40+ issues. This design documents the technical approach for the subset of issues being addressed in this change: three live bugs, a security hole, dead code spread across 6 services, consolidation of duplicate logic, and the missing README/render.yaml gaps. Issues not in scope (Postgres ticket migration, Alembic migrations, OTLP tracing, Redis semantic cache, per-action Pydantic payload models) are deferred — they require more invasive changes.

Current pain points:
- **Silent memory bug**: `retriever.py` builds episodic memory chunks with key `"text"` but `reasoner.py` reads `"content"` — LLM receives empty strings for all past-experience context.
- **Broken concurrency gate**: `semaphore.locked()` pre-check + `semaphore.acquire()` is a TOCTOU race; under exactly-5-concurrent load the guard misfires.
- **Fail-open CSRF**: `verify_csrf_token` returns `True` on missing token or Redis error, neutralising the only HITL forgery control.
- **Unauthenticated audit history**: GET `/history/*` on the audit service has no auth, exposing full action payloads and user IDs to anyone with network access.
- **Dead gateway route**: `GET /v1/approval-callback` is reachable on the public port, bypasses API-key auth, and forwards decisions to the orchestrator — a forge-an-approval path with no legitimate caller.
- **ChromaDB semantic cache**: ~100 lines of cache code built on the wrong tool (vector store metadata, not Redis), unbounded growth, and a correctness bug (stale results after re-ingest). The corpus is 55 documents that Chroma answers in <5ms with no cache.
- **Knowledge `requirements.txt`**: installs `langchain`, `langchain-community`, `asyncpg` (none imported) while omitting `langchain-huggingface` (actually imported) — service may crash at startup unless the dep arrives transitively.

## Goals / Non-Goals

**Goals:**

1. Fix the three live bugs (chunk key, semaphore, CSRF).
2. Remove the unauthenticated audit history endpoints (add `verify_service_token`).
3. Delete the dead gateway approval-callback route (security posture).
4. Delete the ChromaDB semantic cache (correctness + simplicity).
5. Fix knowledge service `requirements.txt` (startup reliability).
6. Move `AuditLogRequest` to `shared/models/audit.py` (single source of truth for the cross-service contract).
7. Extract `_mutate_ticket()` helper in `ticket_handler.py` (reduce 3×-duplicated mutation pattern).
8. Fix `prune_stale_checkpoints()` to also delete from `checkpoint_writes` (prevent unbounded Postgres growth).
9. Normalise all service HTTP client construction to `create_async_http_client()`.
10. Fix `seed_data.py` to read from `sample_tickets.json` instead of a hardcoded duplicate list.
11. Restore `README.md` at repo root.
12. Expand `render.yaml` to cover all 5 missing services and set `APPROVAL_URL` for the frontend.
13. Add `data/chroma/` to `.gitignore` and remove the committed binaries from git tracking.
14. Fix approval CSRF to fail-closed; add startup validation for default `hitl_service_token`.

**Non-Goals:**

- Migrating tickets to Postgres (deferred — requires schema design + Alembic setup).
- Adding Alembic versioned migrations (deferred — separate change).
- OTLP/Jaeger distributed tracing (deferred — infrastructure dependency).
- Per-action Pydantic payload models in the action service (deferred — risk of breaking the LLM tool-call flow).
- Redis-based semantic cache replacement (deferred — the correct answer is no cache for this corpus size, already handled by goal #4).
- Frontend UI redesign or Streamlit improvements beyond removing the hardcoded key default.

## Decisions

### D1 — Fix chunk key mismatch with minimal diff

**Decision:** Change key `"text"` to `"content"` in the episodic memory chunk dict built in `retriever.py` (line 87). Also normalise `"score"` → `"relevance_score"` to match the `KnowledgeChunk` schema the other sources use.

**Alternatives considered:**
- Change `reasoner.py` to try both keys — fragile, masks the root cause.
- Define a `ChunkDict` TypedDict and validate at build time — correct but out of scope for a bug fix.

**Rationale:** Smallest safe change; fixes the silent failure without touching the reasoner.

---

### D2 — Fix semaphore with `asyncio.wait_for`

**Decision:** Replace the `semaphore.locked()` pre-check + `semaphore.acquire()` pair with a single atomic `asyncio.wait_for(semaphore.acquire(), timeout=0.0)` call. A `TimeoutError` means no slot is available; raise `HTTP 503` immediately.

**Alternatives considered:**
- `asyncio.Semaphore.acquire()` with no timeout — blocks indefinitely, no overflow protection.
- `BoundedSemaphore` — same TOCTOU problem without the timeout fix.

**Rationale:** `asyncio.wait_for(..., timeout=0.0)` is atomic with respect to the event loop; there is no gap between the availability check and the acquisition. Clean, idiomatic, zero extra dependencies.

---

### D3 — CSRF fail-closed

**Decision:** In `verify_csrf_token`, change `return True` (the fail-open fallback on missing token or Redis error) to `return False`. Remove the "test environment" comment justifying the bypass.

**Rationale:** The CSRF token is the only forgery control on the human-approval endpoint. Fail-open on infrastructure error defeats the purpose entirely. Tests that need to bypass CSRF should mock the Redis client, not rely on production code to be lenient.

---

### D4 — Audit history authentication

**Decision:** Add `_token: str = Depends(verify_service_token)` to `GET /history/{session_id}` and `GET /history/user/{user_id}` in `audit/main.py`.

**Rationale:** These endpoints return full action payloads, reasoning text, and user IDs. There is no reason for them to be publicly accessible when every other mutating endpoint in the service is protected.

---

### D5 — Delete gateway approval-callback route entirely

**Decision:** Remove the `/v1/approval-callback` route from `services/gateway/main.py`, its `_BYPASS_PATHS` entry in `middleware/auth.py`, and its test coverage in `tests/unit/test_gateway.py`.

**Alternatives considered:**
- Restrict to internal network only — Render free-tier does not support private networking without paid plans; can't enforce at the infra layer.
- Keep it but document it — a documented public forge-an-approval route is worse than no route.

**Rationale:** The approval service posts decisions directly to the orchestrator (`orchestrator_url/approval-callback`). The gateway route has zero legitimate callers in the real system and is a security liability.

---

### D6 — Delete ChromaDB semantic cache, no replacement

**Decision:** Remove the entire semantic cache block from `retriever.py` (lines 119–218 of the original), remove the `query_cache_col` collection creation from `knowledge/main.py`, and remove `"query_cache"` from the collections dict.

**Alternatives considered:**
- Replace with Redis + TTL — correct engineering, but the corpus is 55 docs; Chroma answers in <5ms; adding Redis cache complexity has no measurable benefit at this scale.
- Keep cache but fix the stale-on-ingest bug — still wrong tool, still unbounded growth.

**Rationale:** Simpler is correct. The cache has a correctness bug, uses the wrong backend, and provides no meaningful speedup. Delete it.

---

### D7 — `AuditLogRequest` into `shared/models/audit.py`

**Decision:** Create `shared/models/audit.py` with the `AuditLogRequest` Pydantic model. Update `audit/main.py` to import from shared. Update `audit/audit_store.py` to accept an `AuditLogRequest` and call `.model_dump()` internally. Update all three producers (`action/audit_client.py`, no change needed — it already builds the right fields) to import and construct `AuditLogRequest`.

**Alternatives considered:**
- Keep the local model but add a type check — still 4 copies of the field list.

**Rationale:** The audit contract is a cross-service API; it belongs in `shared/models/` next to the other cross-service contracts.

---

### D8 — `_mutate_ticket()` helper

**Decision:** Extract a private `_mutate_ticket(ticket_id, new_status, extra_fields)` function in `ticket_handler.py`. It handles: validate ticket_id non-empty, acquire lock, load tickets, find ticket (raise if not found), apply `new_status` + `extra_fields` to the ticket dict, save, log, return the result dict. Each of the three public functions (`execute_escalate`, `execute_request_info`, `execute_close`) becomes a thin wrapper that validates its own arguments and calls `_mutate_ticket`.

**Rationale:** The three handlers are 97% identical. Any future change (e.g., adding an audit timestamp to mutations) currently requires three edits in sync.

---

### D9 — Replace Redis distributed lock with `threading.Lock`

**Decision:** Remove `_get_redis_client()`, `_get_db_lock()`, and all Redis imports from `ticket_handler.py`. Replace with a module-level `_tickets_lock = threading.Lock()`. Use it as `with _tickets_lock:` in the same positions the Redis context manager was used.

**Rationale:** The Redis distributed lock guards a local JSON file that is only accessed by this single service process. A second replica would have its own file copy, so the distributed lock never coordinated anything cross-process. The Redis dep in this file added 40 lines of failure-path code for zero benefit.

---

### D10 — Fix `prune_stale_checkpoints`

**Decision:** Add a `DELETE FROM checkpoint_writes WHERE thread_id IN (...)` statement to the existing pruning transaction in `orchestrator/main.py`. The subquery is identical to the one already used for the `checkpoints` table. Increment the `deleted_counts["checkpoint_writes"]` counter correctly.

**Rationale:** LangGraph's `PostgresSaver` creates both `checkpoints` and `checkpoint_writes` entries per checkpoint. The current pruner only cleans the former. On a free-tier Supabase instance (500MB limit), the `checkpoint_writes` table will fill storage first.

## Risks / Trade-offs

- **[Risk] Deleting the gateway callback route breaks tests** → Mitigation: Delete the corresponding test in `test_gateway.py` along with the route; add a note in the PR description.
- **[Risk] CSRF fail-closed could reject legitimate approvals if Redis has a transient error** → Mitigation: Acceptable trade-off; the Redis client already has retry/backoff built in. An approval during a genuine Redis outage should be retried by the human, not silently auto-approved.
- **[Risk] Adding auth to audit history breaks any existing internal consumers** → Mitigation: All consumers are internal Python services that already have the service token; updating their requests is trivial (same `service_headers()` call used everywhere else). No external consumers.
- **[Risk] `_mutate_ticket` refactor may miss a subtle per-handler difference** → Mitigation: Cover the three handlers in the existing `test_action.py` suite; all tests must pass before merging.
- **[Risk] Removing `data/chroma/` from git history requires a force-push if collaborators have clones** → Mitigation: Solo project per context; `git rm -r --cached data/chroma/` + `.gitignore` entry is sufficient (no need for `git filter-repo`).

## Migration Plan

1. Apply changes service-by-service, starting with `shared/models/audit.py` (no runtime impact until consumers are updated).
2. Fix bugs next (chunk key, semaphore, CSRF) — each is a targeted one-line-to-five-line change.
3. Delete dead code (gateway route, ChromaDB cache, ticket Redis lock) — remove, then verify tests pass.
4. Fix `knowledge/requirements.txt` — rebuild the Docker image and confirm startup succeeds.
5. Create `README.md` and expand `render.yaml`.
6. Run `git rm -r --cached data/chroma/` and commit `.gitignore` update last (no code impact).

Rollback: Every change is independently revertable via `git revert`. No database migrations are included, so rollback carries zero schema risk.
