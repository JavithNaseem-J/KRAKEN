## Context

The AKEA system relies on vector search to retrieve relevant FAQs, SLA compliance guidelines, and historic ticket resolutions during agent reasoning. Currently, the Knowledge service (`services/knowledge/`) uses ChromaDB stored on local disk (`./data/chroma`). When deployed to cloud environments (e.g. Render, Railway, AWS ECS without persistent volumes), container restarts wipe the local disk, causing retrieval failures until `make ingest` or `POST /ingest` is manually triggered.

Migrating to **Qdrant Cloud** provides a fully managed, persistent cloud vector database solution, removing local disk state dependencies while supporting payload indexing and efficient multi-source filtering.

## Goals / Non-Goals

**Goals:**
- Replace `chromadb` with `qdrant-client` across `services/knowledge/` and `scripts/ingest_knowledge.py`.
- Consolidate multiple vector collections into a single `akea_knowledge` collection using Qdrant payload filters (`source: "faq" | "sla" | "tickets"`).
- Maintain 100% backward compatibility for `POST /retrieve`, `POST /ingest`, and `GET /stats` API contracts.
- Support local fallback (e.g. in-memory Qdrant client `:memory:`) for offline execution and unit testing without requiring live credentials.

**Non-Goals:**
- Changing the local BGE embedding model (`BAAI/bge-small-en`).
- Modifying pgvector episodic memory in `services/memory/` (pgvector remains dedicated to short-term/long-term session memory).

## Decisions

### 1. Unified Collection with Payload Filtering over Multi-Collection
- **Decision**: Store all knowledge chunks in a single Qdrant collection named `akea_knowledge` and attach a `"source"` string field to each point's payload.
- **Rationale**: Reduces client connection overhead, simplifies schema management, and allows single-pass multi-source retrieval using Qdrant `FieldCondition` filtering.
- **Alternatives Considered**: 3 separate collections (`akea_faq`, `akea_sla_policies`, `akea_sample_tickets`). Rejected due to unnecessary network fan-out overhead over HTTP/gRPC.

### 2. Client-Side BGE Embedding Generation
- **Decision**: Continue generating 384-dimensional dense vectors using `BGEEmbedder` (`BAAI/bge-small-en`) on the client side before uploading to Qdrant Cloud.
- **Rationale**: Preserves exact embedding characteristics, works seamlessly offline, and avoids vendor lock-in to Qdrant FastEmbed.
- **Alternatives Considered**: Qdrant Server-side FastEmbed. Rejected to keep embedding logic consistent and local test execution deterministic.

### 3. Graceful Fallback for Unit Tests
- **Decision**: If `QDRANT_URL` or `QDRANT_API_KEY` is not provided in environment settings, instantiate `QdrantClient(location=":memory:")` for unit testing.
- **Rationale**: Ensures `pytest` unit test suite passes offline without network calls or external API keys.

## Risks / Trade-offs

- **[Risk] Cloud Network Latency**: Remote API calls to Qdrant Cloud could introduce ~20-50ms network round-trip overhead compared to local disk ChromaDB.
  - *Mitigation*: Qdrant gRPC/HTTPS queries are optimized; top_k = 5 payloads are small; 50ms latency is well within the 60s LLM execution budget.
- **[Risk] Missing API Keys in Dev Environment**: Developers without Qdrant API keys could face startup errors.
  - *Mitigation*: Fall back gracefully to `:memory:` in `dev` mode when `QDRANT_URL` is unconfigured.

## Migration Plan

1. Add `qdrant-client>=1.9.0` to `services/knowledge/requirements.txt` and `requirements.txt`; remove `chromadb`.
2. Update `shared/config.py` and `.env.example` with `QDRANT_URL`, `QDRANT_API_KEY`, and `QDRANT_COLLECTION_NAME`.
3. Update `services/knowledge/main.py`, `services/knowledge/retriever.py`, and `scripts/ingest_knowledge.py` to use `QdrantClient`.
4. Update unit test suite in `tests/unit/test_knowledge.py`.
5. Remove obsolete `./data/chroma` references from documentation and `.gitignore`.
