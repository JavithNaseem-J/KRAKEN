## 1. Critical Runtime Bug Remediation

- [x] 1.1 Fix missing `await` on `get_collection()` in `services/knowledge/main.py` (`GET /stats`)
- [x] 1.2 Move `_upsert_chunks` into `services/knowledge/ingest.py` and update it to use `AsyncQdrantClient` for container-safe HTTP ingestion
- [x] 1.3 Implement container-aware data directory resolution in `services/knowledge/loaders/base.py`
- [x] 1.4 Fix episodic memory relevance score parsing in `services/orchestrator/graph/nodes/retriever.py` (`similarity` key mapping)
- [x] 1.5 Delete stale/broken `tests/integration/test_retriever.py`

## 2. Consolidation & Refactoring

- [x] 2.1 Create generic `load_chunks()` helper in `services/knowledge/loaders/base.py` and refactor `ticket_loader`, `sla_loader`, and `faq_loader`
- [x] 2.2 Relocate `BGEEmbedder` to `shared/embedder.py` and reuse across `knowledge` and `memory` services
- [x] 2.3 Add `EpisodeSearchRequest`, `EpisodeSearchResponse`, and `EpisodeChunk` to `shared/models/memory.py`
- [x] 2.4 Consolidate Qdrant client fallback logic in `shared/cache.py`

## 3. Dead Code & Stale Asset Cleanup

- [x] 3.1 Remove dead retrieval cache functions (`get_retrieval_cache`, `set_retrieval_cache`) and unused `create_http_client`
- [x] 3.2 Remove unused `_port` settings from `shared/config.py`
- [x] 3.3 Remove no-op `invalidate_retrieval_cache` call and stale `data/chroma` volume mount from `docker-compose.yml`
- [x] 3.4 Clean stale ChromaDB references in `README.md`, `docs/architecture.md`, and loader docstrings

## 4. Async Event-Loop Hardening & Verification

- [x] 4.1 Offload CPU-bound embedding invocations to `asyncio.to_thread` in `services/knowledge/retriever.py` and `services/memory/long_term.py`
- [x] 4.2 Run `uv run pytest tests/unit/ -v` to ensure 100% test pass rate
