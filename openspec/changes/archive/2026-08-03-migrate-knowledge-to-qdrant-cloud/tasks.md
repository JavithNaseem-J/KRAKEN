## 1. Dependencies and Configuration

- [x] 1.1 Replace `chromadb` with `qdrant-client>=1.9.0` in `services/knowledge/requirements.txt` and root `requirements.txt`
- [x] 1.2 Add `qdrant_url`, `qdrant_api_key`, and `qdrant_collection_name` to `shared/config.py` `Settings`
- [x] 1.3 Update `.env.example` with `QDRANT_URL`, `QDRANT_API_KEY`, and `QDRANT_COLLECTION_NAME`

## 2. Ingestion Pipeline Migration

- [x] 2.1 Update `scripts/ingest_knowledge.py` to instantiate `QdrantClient` (with in-memory fallback if URL is empty) and create the `akea_knowledge` collection (384-dim, Cosine)
- [x] 2.2 Refactor `_upsert` in `scripts/ingest_knowledge.py` to upload `PointStruct` batches containing document content and source payload fields to Qdrant

## 3. Knowledge Service Implementation

- [x] 3.1 Refactor `services/knowledge/main.py` lifespan to initialize `QdrantClient` and ensure the `akea_knowledge` collection exists
- [x] 3.2 Refactor `services/knowledge/retriever.py` `KnowledgeRetriever` to store the `QdrantClient` instance
- [x] 3.3 Update `KnowledgeRetriever.retrieve()` in `services/knowledge/retriever.py` to execute vector searches with `source` payload filters and map results back to `KnowledgeChunk` models
- [x] 3.4 Update `GET /stats` in `services/knowledge/main.py` to return Qdrant collection point count

## 4. Verification and Testing

- [x] 4.1 Update `tests/unit/test_knowledge.py` to test `QdrantClient` in-memory fallback and search endpoints
- [x] 4.2 Run `pytest tests/unit/test_knowledge.py -v` to ensure unit tests pass without external network dependencies
- [x] 4.3 Run `ruff check . && ruff format --check .` to ensure 0 style/lint errors
