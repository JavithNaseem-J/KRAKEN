## Context

The AKEA codebase has 28 confirmed structural debt items identified by a full-repo audit. Three of these are active runtime crashes. The rest fall into duplicate logic, dead code, and inconsistent pattern categories. All fixes are implementation-layer changes — no API contracts, database schemas, or service boundaries change. The system uses FastAPI + LangGraph + Redis + PostgreSQL + ChromaDB across seven microservices with a shared `shared/` package.

## Goals / Non-Goals

**Goals:**
- Eliminate 3 runtime crashes (NameError, AttributeError, ValueError) that are active right now.
- Remove all confirmed dead code (unused imports, unreferenced variables).
- Collapse all duplicate logic into shared helpers.
- Restore consistent cross-service patterns (module-level settings, shared HTTP factory, env-var-sourced URLs).
- Leave CI (`ruff check`, `mypy`, `pytest tests/unit`) passing cleanly after every commit.

**Non-Goals:**
- No feature additions.
- No API contract changes.
- No database schema changes.
- No performance or scalability improvements (tracked separately in REPORT2).
- No changes to LangGraph topology or agent graph nodes beyond the `memory_url` rename.

## Decisions

### D1 — Fix crashes as isolated atomic commits

**Decision:** Each of the three runtime crashes is fixed in a standalone, reviewable commit before any refactor work begins.

**Rationale:** A crash fix is the smallest possible diff — one line. Mixing it with a refactor creates noise in code review and risks reverting the fix if the refactor is rolled back.

**Alternatives considered:**
- "Fix everything in one PR" — rejected because a broken import (NameError) means CI can't even run the action-service tests; the crash must be fixed first or CI stays broken.

---

### D2 — Extend `shared/http_client.py` rather than creating a new module

**Decision:** Add `service_headers()` and update `create_async_http_client()` to accept an `httpx.Timeout` object directly in the existing `shared/http_client.py`.

**Rationale:** The module already exists and is the canonical home for cross-service HTTP concerns. Creating a new module (`shared/http_factory.py`) would add indirection.

**Alternatives considered:**
- Per-service factory — rejected because the whole point is to eliminate per-service duplication.

---

### D3 — `atomic_write_json` returns `int` (bytes written)

**Decision:** Change `atomic_write_json(target_path, content) -> None` to `-> int` (returns `len(json_bytes)`). Update all callers.

**Rationale:** `write_handler.py` needs the byte count to log it. Currently it double-serialises to get it. Returning it from the canonical writer eliminates the duplication without changing the write behaviour.

**Alternatives considered:**
- Keep `-> None` and accept the double serialisation — rejected because it is measurably wasteful and the fix is trivial.
- A separate `json_byte_size(content)` helper — rejected as more code than needed.

---

### D4 — Extract `_find_ticket()` into `ticket_handler.py` module scope

**Decision:** Add `_find_ticket(tickets: list[dict], ticket_id: str) -> dict | None` as a private module-level helper inside `ticket_handler.py`.

**Rationale:** All four handlers already import from the same module; no new import is needed. The helper is not general enough to live in `shared/`.

---

### D5 — Fix ingest script by delegating to the service's `_run_ingest` logic

**Decision:** Replace the re-implementation in `scripts/ingest_knowledge.py` with a call to the shared loader functions that `services/knowledge/main.py`'s `_run_ingest()` already calls. Both paths call the same loader imports.

**Rationale:** The script exists for offline/pre-seed use (before the service starts), so it cannot call the HTTP endpoint. The correct fix is to have both the script and the HTTP handler import the same `load_*_chunks()` functions — which they already do — and remove the diverging ChromaDB client setup in the script by aligning it with the service pattern.

**The specific bug** (line 95: `chunks, _ = load_ticket_chunks()`) is a 1-line fix. The broader duplication cleanup is a separate, lower-priority task.

---

### D6 — Approval URL in frontend reads from `APPROVAL_URL` env var

**Decision:** Replace the two hardcoded `http://localhost:8004` strings in `frontend/app.py` with `os.getenv("APPROVAL_URL", "http://localhost:8004")` resolved once at module level.

**Rationale:** Identical to how `GATEWAY_URL` is handled on line 17 of the same file.

## Risks / Trade-offs

- **`atomic_write_json` return type change** → Any caller that currently ignores the return value is unaffected (Python ignores `None` vs `int` at call sites). The only caller that uses the value is `write_handler.py` — which is the target of the change. Risk: **Low**.

- **Removing unused imports** → `ruff` already flags these; removing them is safe. The only risk is a false positive where an import is used via `__all__` re-export — confirmed not the case for `secrets` or `Header` in any of the five affected files. Risk: **None**.

- **`_find_ticket()` extraction** → The four handler functions currently have slightly different context variable names (`found`, `updated_ticket`). The helper unifies them. Existing unit tests for handlers will catch any regression. Risk: **Low**.

- **`memory_url` rename in orchestrator** → This is a single string change from `settings.memory_service_url` → `settings.memory_url`. The field exists with that name in `shared/config.py`. The fix restores previously broken behaviour — it cannot make things worse. Risk: **None**.

## Migration Plan

1. Fix 3 runtime crashes (commits 1–3, trivial diffs).
2. Remove all unused imports across 5 files (commit 4, mechanical).
3. Extend `shared/http_client.py` and update callers (commit 5).
4. Fix `atomic_write_json` return type and update `write_handler.py` (commit 6).
5. Extract `_find_ticket()` helper (commit 7).
6. Fix ingest script tuple-unpack (commit 8, one line).
7. Fix `audit_client.py` settings pattern (commit 9, one line).
8. Fix approval queue TTL + docstring (commit 10).
9. Fix frontend approval URL (commit 11).
10. Fix in-function imports in `retriever.py` (commit 12).
11. Run `ruff check .`, `mypy shared/ services/`, `pytest tests/unit` — all must pass.

No deployment coordination required. Each commit is independently deployable.
