## 1. Security & Access Control

- [x] 1.1 Fix CSRF token validation in `services/approval/main.py` (make `csrf_token: str = Form(...)` mandatory and fail closed) (C-1)
- [x] 1.2 Implement per-service secret tokens and environment validation in `shared/auth.py` and `shared/config.py` (C-2)
- [x] 1.3 Add `.env` to `.gitignore`, remove committed token from `.env`, and update `.env.example` (C-5)
- [x] 1.4 Require service token authentication for `GET /queue/stats` in `services/approval/main.py` (I-6)
- [x] 1.5 Add Pydantic input validation (length + pattern regex) for `session_id` and `user_id` in `QueryRequest` (I-5)

## 2. Async Concurrency & Performance

- [x] 2.1 Upgrade `services/knowledge/retriever.py` and `services/knowledge/main.py` to use `AsyncQdrantClient` for non-blocking retrieval (C-3)
- [x] 2.2 Refactor `BGEEmbedder` in `services/knowledge/embedder.py` to remove ChromaDB inheritance and dependencies (C-4)
- [x] 2.3 Convert `decider_node`, `reasoner_node`, and `responder_node` to `async def` and use `await llm.ainvoke()` (I-2)
- [x] 2.4 Refactor `memory_writer_node` to use `asyncio.create_task` with shared async `httpx` client (I-3)
- [x] 2.5 Implement hybrid vector + sparse search with RRF fusion in `KnowledgeRetriever` (I-7)

## 3. Quality, Parameterized Maintenance & Test Fixes

- [x] 3.1 Replace hardcoded `"change-me-in-production"` default test tokens with valid 64-char test tokens in test fixtures (C-6)
- [x] 3.2 Rewrite `prune_stale_checkpoints` SQL queries to use parameterized CTEs instead of f-string formatting (C-7)
- [x] 3.3 Fix unit test patch target in `tests/unit/test_orchestrator.py` to correctly patch `httpx.AsyncClient` (I-9)

## 4. Deployment & Operational Tuning

- [x] 4.1 Optimize semantic cache client initialization and async lookup for low latency (I-1)
- [x] 4.2 Increase gateway default rate limit to `60 req/60s` in `shared/config.py` (I-8)
- [x] 4.3 Add `healthCheckPath: /health` and set `plan: starter` for core services in `render.yaml` (I-4, I-10)

## 5. Verification & Evaluation

- [x] 5.1 Run `pytest` unit test suite to verify 100% test pass rate
- [x] 5.2 Validate OpenSpec artifacts and status
