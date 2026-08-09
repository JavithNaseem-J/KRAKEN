## 1. Pydantic Document Ingestion Schemas

- [x] 1.1 Create `TicketDocument`, `FAQDocument`, `SLADocument`, and `KnowledgeChunkPayload` models in `shared/models/knowledge.py`.
- [x] 1.2 Update `services/knowledge/loaders/ticket_loader.py` to validate raw JSON records against `TicketDocument` before chunking.
- [x] 1.3 Update `services/knowledge/loaders/faq_loader.py` and `sla_loader.py` to use Pydantic model validation.
- [x] 1.4 Update `services/knowledge/ingest.py` to validate Qdrant point payloads against `KnowledgeChunkPayload`.

## 2. PostgreSQL Connection Pool Keep-Alives & Stabilization

- [x] 2.1 Update `shared/config.py` to include TCP keep-alive settings (`keepalives=1`, `keepalives_idle=30`, `keepalives_interval=10`).
- [x] 2.2 Configure `psycopg_pool.ConnectionPool` in `services/orchestrator/main.py` with `max_idle_lifetime=300.0`, `max_lifetime=1800.0`, and connection recycling.
- [x] 2.3 Configure `psycopg_pool.ConnectionPool` in `services/action/handlers/ticket_handler.py` with TCP keep-alives and auto-reconnection wrappers.

## 3. Decoupled Shared Embedding Provider & Scoring Normalization

- [x] 3.1 Refactor `BGEEmbedder` in `shared/embedder.py` into a thread-safe singleton with `@lru_cache(maxsize=1024)` vector caching.
- [x] 3.2 Update `services/knowledge/main.py` and `services/memory/main.py` to utilize the shared embedder singleton factory.
- [x] 3.3 Verify RRF composite score normalization in `services/knowledge/retriever.py` ensures 0.0–1.0 bounds for all retrieved knowledge chunks.

## 4. Operational Health & Test Verification

- [x] 4.1 Re-run `pytest` suite across all 173+ microservice unit tests to verify zero regressions.
- [x] 4.2 Run `scripts/check_health.py` to confirm HTTP 200 health across all 7 microservices.
