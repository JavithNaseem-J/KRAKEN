## Context

The KRAKEN framework relies on asynchronous FastAPI microservices communicating over HTTP and accessing PostgreSQL (Supabase) and Qdrant Cloud. Under sustained loads or idle periods, three key architectural friction points occur:
1. Untyped dictionary access (`ticket.get("id")` vs `ticket.get("ticket_id")`) in document loaders leads to silent schema mismatches in Qdrant point payloads.
2. `psycopg_pool.ConnectionPool` drops idle SSL sockets due to missing TCP keep-alives when interacting with Supabase PgBouncer poolers.
3. Concurrent container instances duplicate PyTorch model weight loads in memory (~300MB per worker container), delaying startup times by 10-15s.

## Goals / Non-Goals

**Goals:**
- Enforce strict Pydantic V2 schema validation at the document ingestion boundary and vector payload serialization point.
- Configure OS-level TCP keep-alives (`keepalives=1`, `keepalives_idle=30`) and pool idle connection recycling across all PostgreSQL connection pools.
- Refactor `BGEEmbedder` into a process-level thread-safe singleton with `@lru_cache` in-memory vector caching.
- Standardize vector retrieval scoring with a normalized 0.0–1.0 RRF blend.

**Non-Goals:**
- Offloading embedding inference to a standalone gRPC Triton server in this phase (singleton LRU cache achieves <0.5s container startup and eliminates redundancy).
- Changing frontend UI components or API contract endpoints.

## Decisions

### Decision 1: Strict Pydantic Schema Contracts at Ingestion Boundary
- **Choice**: Define `TicketDocument`, `FAQDocument`, `SLADocument`, and `KnowledgeChunkPayload` models in `shared/models/knowledge.py`. Loaders must validate JSON raw records against Pydantic models prior to chunking.
- **Alternatives Considered**: Direct dictionary access with fallback `.get("id") or .get("ticket_id")`. Rejected because fallback chains allow silent data corruption and type drift.

### Decision 2: TCP Keep-Alives & Connection Recycling for PostgreSQL Pools
- **Choice**: Pass `kwargs={"keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 5}` to `psycopg_pool.ConnectionPool` in `services/orchestrator/main.py` and `services/action/handlers/ticket_handler.py`. Set `max_idle_lifetime=300.0`.
- **Alternatives Considered**: Re-opening connection per HTTP request. Rejected due to high latency overhead on every query.

### Decision 3: Thread-Safe Singleton Embedder with LRU Vector Cache
- **Choice**: Implement `get_embedder()` singleton factory in `shared/embedder.py` with `@lru_cache(maxsize=1024)` on `embed_query()`.
- **Alternatives Considered**: Standalone gRPC service container. Deferred to future phase to minimize infrastructure deployment complexity while achieving sub-second container startup times.

## Risks / Trade-offs

- **[Risk] High-volume cache memory growth** → **Mitigation**: Cap `@lru_cache` at `maxsize=1024` vectors (~1.5 MB RAM footprint).
- **[Risk] Supabase network reset during long queries** → **Mitigation**: Set `keepalives_idle=30` and `reconnect_timeout=30.0` in connection pool options.
