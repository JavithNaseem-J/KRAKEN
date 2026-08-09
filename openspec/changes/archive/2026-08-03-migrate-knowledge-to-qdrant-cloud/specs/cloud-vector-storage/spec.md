# cloud-vector-storage Specification

## ADDED Requirements

### Requirement: Qdrant vector database client initialization
The Knowledge Service SHALL initialize a `QdrantClient` during service startup using configuration settings `qdrant_url` and `qdrant_api_key`. If `qdrant_url` is not set or is empty, the service SHALL fall back to an in-memory Qdrant instance (`location=":memory:"`).

#### Scenario: Production Qdrant Cloud connection
- **WHEN** the Knowledge Service starts up with valid `QDRANT_URL` and `QDRANT_API_KEY` environment variables
- **THEN** it SHALL establish a persistent connection to the remote Qdrant Cloud cluster

#### Scenario: Offline unit test fallback
- **WHEN** the Knowledge Service starts up without `QDRANT_URL` configured
- **THEN** it SHALL initialize an in-memory `QdrantClient(location=":memory:")` without attempting external network calls

### Requirement: Single collection vector indexing with payload filtering
The Knowledge Service SHALL store all knowledge chunks in a single Qdrant collection named `akea_knowledge` configured with 384-dimensional Cosine distance vectors. Each point's payload MUST contain `content` (str), `source` (str), `document_id` (str), and `metadata` (dict).

#### Scenario: Ingestion upserts points with payload metadata
- **WHEN** `scripts/ingest_knowledge.py` or `POST /ingest` is executed
- **THEN** it SHALL convert knowledge chunks into 384-dimensional dense vectors using `BGEEmbedder` and upsert points containing source payload labels into `akea_knowledge`

#### Scenario: Filtered multi-source vector retrieval
- **WHEN** `POST /retrieve` is called with a query and target sources `["faq", "sla"]`
- **THEN** the retriever SHALL execute a single vector search query against `akea_knowledge` filtered by `source` payload conditions, returning top-k ranked `KnowledgeChunk` objects
