## Context

Following the high-severity and medium-severity debt cleanups, this design addresses the remaining 6 low-severity codebase audit findings to ensure pristine dev setup, clean Docker deployment builds, zero dead code, and unified API keys.

## Goals / Non-Goals

**Goals:**
- Delete unreferenced `scratch_schema.py` root script.
- Standardize all 6 microservice `Dockerfile`s onto UTF-8 multi-stage build patterns.
- Ensure root `requirements.txt` is an exact union of service requirements.
- Standardize default dev API keys across all test harnesses, benchmark scripts, and frontend code to `dev-key-alice-longer-secure-key`.
- Delete unused variables (`_ALL_SOURCES`) and dead model fields (`ActionResult.requires_hitl`, `approval_id`).
- Optimize gateway startup by parsing API keys once at module level.

**Non-Goals:**
- Modifying microservice port mappings or core service architectures.
- Changing production auth models or breaking API contracts.

## Decisions

1. **API Key Uniformity**:
   Standardize on `dev-key-alice-longer-secure-key:alice,dev-key-bob-longer-secure-key:bob`. Clients default to `dev-key-alice-longer-secure-key`.
2. **Docker Multi-Stage Build**:
   Convert single-stage Dockerfiles to standard multi-stage builds (`python:3.11-slim`) with non-root user and clean UTF-8 encoding headers.
3. **Gateway Key Caching**:
   Store parsed key dictionary in `app.state.api_keys` at startup and reference it cleanly without duplicate parsing.

## Risks / Trade-offs

- **[Risk]**: Scripts or tests using legacy short keys (`dev-key-1`, `dev-key-alice`) will fail authentication against the gateway if not updated.
- **[Mitigation]**: Update all client scripts (`frontend/app.py`, `scripts/benchmark.py`, `tests/evals/eval_harness.py`, `.env.example`) simultaneously.
