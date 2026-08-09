## Why

A comprehensive technical audit of AKEA revealed several critical runtime bugs (`GET /stats` missing `await`, `POST /ingest` client/Docker image mismatches, loader path resolution failure inside containers, episodic memory relevance score parsing mismatch), severe code duplication (knowledge loaders, embedding initializations, Qdrant client setups), dead code, and event-loop blocking calls in async hot paths.

Remediating these issues is necessary to ensure zero runtime crashes, 100% container stability, correct score reporting in RAG retrieval, and clean maintainable microservice architecture.

## What Changes

- **Fix Critical Runtime Bugs**:
  - Add missing `await` on `get_collection()` in `services/knowledge/main.py:99` (`GET /stats`).
  - Move `_upsert_chunks` into `services/knowledge/` and adapt for `AsyncQdrantClient` to fix `POST /ingest`.
  - Fix data directory path resolution in loaders (`ticket_loader`, `sla_loader`, `faq_loader`) to handle both local and container layout.
  - Fix episodic memory relevance score parsing in `services/orchestrator/graph/nodes/retriever.py` to read `similarity` instead of `score`.
  - Remove stale `tests/integration/test_retriever.py`.
- **Code Duplication & Refactoring**:
  - Refactor `ticket_loader`, `sla_loader`, and `faq_loader` to use a unified generic chunk loader function in `services/knowledge/loaders/base.py`.
  - Move `BGEEmbedder` to `shared/embedder.py` so both `knowledge` and `memory` services reuse it without duplication.
  - Consolidate Qdrant client initialization in `shared/cache.py`.
- **Dead Code & Stale Asset Cleanup**:
  - Remove dead functions `get_retrieval_cache`, `set_retrieval_cache`, and unused sync `create_http_client`.
  - Remove unused `_port` settings from `shared/config.py`.
  - Remove no-op `invalidate_retrieval_cache` wiring and stale `data/chroma` volume mount from `docker-compose.yml`.
  - Clean stale docstrings and update documentation (`README.md`, `docs/architecture.md`) referencing ChromaDB.
- **Async & Data Contract Hardening**:
  - Wrap CPU-bound sentence-transformer embedding calls in `asyncio.to_thread` / `run_in_executor` in `retriever.py` and `long_term.py`.
  - Add `EpisodeSearchRequest`, `EpisodeSearchResponse`, `EpisodeChunk` to `shared/models/memory.py` to strictly type the memory service boundary.

## Capabilities

### New Capabilities
- `knowledge-loader-consolidation`: Unified, robust loader framework and container-safe path resolution for knowledge ingestion.

### Modified Capabilities
- `knowledge-cache`: Non-blocking async Qdrant operations, clean cache API, and proper `GET /stats` reporting.
- `orchestrator-concurrency-control`: Async event-loop non-blocking node execution and correct episodic memory score handling.

## Impact

- **Services**: `services/knowledge/`, `services/memory/`, `services/orchestrator/`, `shared/`
- **Tests**: `tests/unit/`, `tests/integration/`
- **Deployment**: `docker-compose.yml`, `README.md`, `docs/architecture.md`
