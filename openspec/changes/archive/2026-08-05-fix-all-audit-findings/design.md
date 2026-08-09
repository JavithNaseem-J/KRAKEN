## Context

A technical audit of the AKEA system uncovered 17 specific vulnerabilities and architectural flaws categorized into CRITICAL items (e.g. bypassable CSRF, flat trust secret model, synchronous vector DB calls in async event loop, hardcoded test secrets, f-string SQL queries) and IMPROVEMENT items (e.g. sync LLM invocations, unauthenticated stats endpoints, low rate limits, missing Render health checks, dense-only RAG).

This design details the technical architecture and code-level modifications required to fix all 17 findings systematically across the repository.

## Goals / Non-Goals

**Goals:**
- Eliminate all 7 CRITICAL security and concurrency flaws.
- Implement all 10 IMPROVEMENT recommendations across security, performance, quality, and deployment.
- Maintain full backwards compatibility for API contracts (`QueryRequest`, `QueryResponse`).
- Pass all unit, integration, and evaluation harness tests with 100% compliance.

**Non-Goals:**
- Complete rewrite of the microservices architecture into a monolith.
- Replacing FastAPI or LangGraph with alternative frameworks.

## Decisions

### 1. Mandatory CSRF & Authentication Enforcement (C-1, I-6)
- **Decision**: In `services/approval/main.py`, modify `submit_decision` signature to `csrf_token: str = Form(...)` (mandatory). Remove `if csrf_token is not None`.
- **Rationale**: Eliminates the CSRF validation bypass vector.
- **Decision**: Add `_token: str = Depends(verify_service_token)` to `GET /queue/stats`.

### 2. Per-Service Token Secret Model & Hygiene (C-2, C-5, C-6)
- **Decision**: Update `shared/auth.py` and `shared/config.py` to support explicit per-service pair tokens while maintaining fallbacks for backward compatibility. Add `.env` to `.gitignore`. Update unit tests to generate and monkeypatch a valid 64-character test token instead of `"change-me-in-production"`.

### 3. Fully Asynchronous Knowledge Retrieval & Vector DB Client (C-3, C-4, I-7)
- **Decision**: Upgrade `services/knowledge/main.py` and `retriever.py` to use `AsyncQdrantClient`. Change `self._client.search(...)` to `await self._client.search(...)`.
- **Decision**: Refactor `BGEEmbedder` to wrap `HuggingFaceEmbeddings` directly without subclassing ChromaDB's `EmbeddingFunction`. Remove `chromadb` dependency, `CHROMA_PERSIST_DIR`, and volume mounts.
- **Decision**: Implement hybrid vector + sparse search with RRF fusion in `KnowledgeRetriever`.

### 4. Asynchronous Graph Nodes & Consolidated Memory Writer (I-2, I-3, I-9)
- **Decision**: Convert `decider_node`, `reasoner_node`, and `responder_node` to `async def` and use `await llm.ainvoke(...)`.
- **Decision**: Refactor `memory_writer_node` to use `asyncio.create_task` with `app.state.http` (async client), eliminating the standalone sync HTTP client and thread pool.
- **Decision**: Fix unit test in `test_orchestrator.py` to patch `httpx.AsyncClient` correctly.

### 5. Parameterized Maintenance Queries & Input Validation (C-7, I-5)
- **Decision**: Rewrite SQL in `prune_stale_checkpoints` using parameterized CTEs to eliminate string formatting.
- **Decision**: Add Pydantic string validation (length + pattern regex) for `session_id` and `user_id` in `QueryRequest`.

### 6. Production Deployment & Rate Limit Tuning (I-4, I-8, I-10)
- **Decision**: Update `render.yaml` with `healthCheckPath: /health` for all services and set `plan: starter` for orchestrator and approval services.
- **Decision**: Increase `gateway_rate_limit_requests` to 60 req/min in default settings.

## Risks / Trade-offs

- **[Risk]**: `AsyncQdrantClient` in `services/knowledge` might fail if Qdrant Cloud connection drops.
  - **Mitigation**: Wrap Qdrant calls with retry logic and graceful fail-open error handling.
- **[Risk]**: Per-service tokens could increase configuration overhead in dev environment.
  - **Mitigation**: Default values in `dev` environment fall back cleanly while strict validation is enforced in `prod`.

## Migration Plan

1. Apply code refactors across shared library, services, docker configs, and unit tests.
2. Run `pytest` unit test suite to verify 100% pass rate.
3. Run evaluation harness `tests/evals/eval_harness.py` to verify operational scoring.
4. Verify Render IaC configuration via `openspec validate`.

## Open Questions

- None. All 17 audit items have clear, actionable remedies.
