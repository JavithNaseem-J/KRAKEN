## Why

The Knowledge Service (`services/knowledge/`) currently uses ChromaDB with local disk persistence (`CHROMA_PERSIST_DIR`). When deployed to cloud container platforms like Render or Railway, free-tier ephemeral container disks are wiped on container restarts or re-deployments, causing loss of vector embeddings until manual ingestion is run. Migrating to Qdrant Cloud provides enterprise-grade, managed cloud vector storage with zero local storage dependencies, unified payload filtering, and high-performance gRPC/HTTPS vector search.

## What Changes

- **Qdrant Cloud Integration**: Replace ChromaDB (`chromadb`) with Qdrant Cloud (`qdrant-client`) in the Knowledge service.
- **Unified Vector Collection**: Consolidate the 3 Chroma collections (`akea_faq`, `akea_sla_policies`, `akea_sample_tickets`) into a single Qdrant collection (`akea_knowledge`) using indexed payload filters (`source: "faq" | "sla" | "tickets"`).
- **Environment Configuration**: Add `QDRANT_URL`, `QDRANT_API_KEY`, and `QDRANT_COLLECTION_NAME` settings to `shared/config.py` and `.env.example`.
- **Ingestion Pipeline**: Update `scripts/ingest_knowledge.py` and `services/knowledge/main.py` to upsert vector points directly to Qdrant Cloud.
- **Retrieval Engine**: Update `services/knowledge/retriever.py` to execute vector searches with Qdrant payload filters.

## Capabilities

### New Capabilities
- `cloud-vector-storage`: Managed cloud vector search and indexing via Qdrant Cloud with payload filtering for multi-source knowledge retrieval.

### Modified Capabilities
- *(None — existing system interface `POST /retrieve` and `POST /ingest` remain unchanged)*

## Impact

- **Dependencies**: Remove `chromadb` dependency from `services/knowledge/requirements.txt` and `requirements.txt`; add `qdrant-client>=1.9.0`.
- **Configuration**: `QDRANT_URL` and `QDRANT_API_KEY` required in `.env` for cloud deployments (falls back to local in-memory Qdrant instance for unit tests).
- **Services Affected**: `services/knowledge/` (main, retriever, requirements), `scripts/ingest_knowledge.py`, `shared/config.py`, `render.yaml`.
