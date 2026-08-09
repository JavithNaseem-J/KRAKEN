# multi-tier-caching Specification

## ADDED Requirements

### Requirement: Semantic LLM response caching via Qdrant
The system SHALL maintain a dedicated Qdrant collection `akea_semantic_cache` to store prompt vector embeddings and their corresponding LLM responses. When an incoming query has Cosine similarity $\ge 0.92$ with a cached vector, the system SHALL immediately return the cached response without invoking the LLM.

#### Scenario: Semantic cache hit
- **WHEN** a user query matches a stored vector in `akea_semantic_cache` with similarity $\ge 0.92$
- **THEN** the system SHALL return the cached answer in <30ms and increment the cache hit log metric

#### Scenario: Semantic cache miss
- **WHEN** a user query has similarity $< 0.92$ with all cached vectors
- **THEN** the system SHALL proceed with standard RAG retrieval and LLM generation, storing the new response in `akea_semantic_cache`

### Requirement: Invalidation of vector retrieval cache on knowledge ingestion
The Knowledge Service SHALL cache vector retrieval query lookups in Redis under keys `retrieval:<hash>`. When `POST /ingest` is executed, the Knowledge Service SHALL invalidate all `retrieval:*` keys from Redis.

#### Scenario: Ingestion invalidates cached retrieval lookups
- **WHEN** `POST /ingest` completes
- **THEN** all `retrieval:*` Redis keys SHALL be purged, ensuring subsequent searches retrieve freshly ingested documents
