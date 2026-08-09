## Context

The repository has evolved through rapid iterations resulting in critical operational defects, duplication, and stale artifacts. Specifically:
- `services/knowledge/main.py` fails to await `get_collection()` on `AsyncQdrantClient`, causing `GET /stats` to always return 0.
- `POST /ingest` attempts to import `scripts.ingest_knowledge` (which is not included in the Docker build) and passes `AsyncQdrantClient` to sync `upsert()`.
- Knowledge loaders rely on `Path(__file__).resolve().parents[3]`, which breaks under Docker container file layouts.
- `orchestrator/graph/nodes/retriever.py` parses episodic memory results looking for `score` instead of `similarity`, causing all episodic memories to default to `0.8` relevance.
- CPU-bound model embeddings are executed directly on the main event loop thread inside `async def` methods.

## Goals / Non-Goals

**Goals:**
- Eliminate all 5 critical runtime bugs.
- Consolidate loader scanning logic and move `BGEEmbedder` into `shared/embedder.py`.
- Purge dead code, unused functions (`create_http_client`, `get_retrieval_cache`, etc.), dead config settings, and stale Docker mounts/docs.
- Ensure all CPU-heavy embedding calls use `asyncio.to_thread` / `run_in_executor` to avoid event-loop blocking.
- Introduce typed Pydantic models for memory request/response boundaries in `shared/models/memory.py`.

**Non-Goals:**
- Introducing a new vector database framework (Qdrant Cloud remain the standard).
- Refactoring LangGraph state structures or modifying existing graph routing logic.

## Decisions

### Decision 1: Shared Embedder & Async Offload
Move `BGEEmbedder` to `shared/embedder.py`. In `retriever.py` and `long_term.py`, wrap synchronous `embed_query` / `embed_documents` invocations in `asyncio.to_thread(...)` so CPU-bound vector calculations never block event loop execution.

### Decision 2: Unified Container-Aware Knowledge Loader
Create `services/knowledge/loaders/base.py` containing a generic `load_chunks` function. Update `ticket_loader.py`, `sla_loader.py`, and `faq_loader.py` to be thin wrappers passing their specific schema-formatter. Resolve data paths using a fallback strategy: `Path(__file__).resolve().parents[3] / "data"` if present, else `/app/data`.

### Decision 3: Service-Internal Ingestion Execution
Move `_upsert_chunks` out of `scripts/ingest_knowledge.py` into `services/knowledge/ingest.py`. Update it to use `AsyncQdrantClient` natively so `POST /ingest` works cleanly both locally and inside Docker containers.

### Decision 4: Strict Shared Models for Memory Boundaries
Add `EpisodeSearchRequest`, `EpisodeSearchResponse`, and `EpisodeChunk` to `shared/models/memory.py`. Standardize on `similarity` field naming across memory and orchestrator services.

## Risks / Trade-offs

- **[Risk]** Threading overhead for fast single-string embeddings.  
  → *Mitigation:* `bge-small-en` embeddings take ~5-15ms on CPU; offloading to `asyncio.to_thread` prevents event loop starvation during concurrent request bursts.
- **[Risk]** Schema changes in existing JSON/CSV knowledge data.  
  → *Mitigation:* Generic loader handles optional fields defensively and logs parse errors cleanly per file.
