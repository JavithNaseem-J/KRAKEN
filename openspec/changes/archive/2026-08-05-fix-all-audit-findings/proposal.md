## Why

A technical audit of the Autonomous Knowledge Execution Agent (AKEA) codebase identified 7 CRITICAL vulnerabilities and architecture flaws alongside 10 high-value IMPROVEMENT areas spanning security, async event loop blocking, credential handling, testing validity, and deployment configuration. Addressing all 17 findings hardens the agent system against security bypasses, removes severe event-loop bottlenecks, eliminates dead code/legacy artifacts, and ensures enterprise readiness under load.

## What Changes

Fix all 17 technical audit findings across the 4 primary engineering domains:

### Security & Access Control
- **CSRF Token Enforcement (C-1)**: Enforce mandatory CSRF validation on all human approval submissions (`POST /approve/{approval_id}/decision`); reject requests missing tokens with HTTP 403.
- **Service Secret Isolation (C-2)**: Replace flat single-token model (`HITL_SERVICE_TOKEN`) with per-service secret configuration.
- **Secret Hygiene & Git Scrubbing (C-5)**: Remove live service token from `.env`, ensure `.env` is ignored by git, and mandate platform secret manager usage.
- **Unauthenticated Endpoint Security (I-6)**: Require inter-service token validation for `GET /queue/stats` on the approval service.
- **Strict Input Validation (I-5)**: Enforce strict Pydantic length and regex pattern validation on `session_id` and `user_id` across API boundaries.

### Async Concurrency & Performance
- **Non-Blocking Qdrant Retriever (C-3)**: Replace synchronous `QdrantClient.search()` with `AsyncQdrantClient` in `services/knowledge/retriever.py` to prevent event-loop thread blocking.
- **Async LLM Invocations (I-2)**: Convert synchronous `llm.invoke()` calls to `await llm.ainvoke()` across decider, reasoner, and responder graph nodes.
- **Memory Writer Resource Consolidation (I-3)**: Eliminate standalone sync `httpx.Client` and thread pool in `memory_writer.py` in favor of shared async client and non-blocking tasks.
- **Semantic Cache Optimization (I-1)**: Optimize semantic cache storage and lookup layer to meet the <30ms SLA.

### Quality, Architecture & Test Integrity
- **ChromaDB Legacy Cleanup (C-4)**: Remove dead ChromaDB inheritance, dependencies, environment variables, and Docker volume mounts.
- **Test Credential Realism (C-6)**: Replace hardcoded default token `"change-me-in-production"` in unit tests with valid test tokens.
- **Parameterized SQL Execution (C-7)**: Replace f-string SQL query construction in `prune_stale_checkpoints` with parameterized CTE queries.
- **Test Mock Accuracy (I-9)**: Fix `retriever_node` unit test mock target to correctly patch `httpx.AsyncClient`.
- **Hybrid RAG Capability (I-7)**: Upgrade knowledge retrieval to hybrid vector + sparse search with RRF fusion.

### Deployment & Scale Operations
- **Render Production Health Checks (I-10)**: Configure `healthCheckPath: /health` for all services in `render.yaml`.
- **Render Service Tier Upgrade (I-4)**: Update `render.yaml` service plans from `free` to `starter` for core services to eliminate cold-start HITL failures.
- **Enterprise Rate Limit Alignment (I-8)**: Adjust default rate limits from 10 req/min to enterprise-grade thresholds with role-aware configuration.

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `approval-security-guardrail`: Enforce non-optional CSRF verification on approval submission.
- `secrets-management`: Separate inter-service credentials and enforce environment hygiene.
- `orchestrator-concurrency-control`: Enforce async non-blocking execution across Qdrant retrieval, LLM node invocation, and background memory writes.
- `knowledge-cache`: Clean up legacy ChromaDB references and optimize semantic cache lookup.
- `docker-standardization`: Update Render deployment configs with health check probes and service tiers.

## Impact

- **Affected Services**: `gateway`, `orchestrator`, `knowledge`, `action`, `approval`, `memory`, `audit`.
- **APIs**: `POST /approve/{approval_id}/decision`, `GET /queue/stats`, `POST /v1/run`, `POST /retrieve`.
- **Dependencies**: Remove `chromadb` dependency from `services/knowledge/requirements.txt`.
- **Database**: SQL queries in orchestrator checkpoint maintenance rewritten to parameterized form.
