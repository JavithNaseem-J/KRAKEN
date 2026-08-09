## MODIFIED Requirements

### Requirement: Semantic cache uses non-blocking async Qdrant client
The `SemanticCache` in `shared/cache.py` SHALL use `qdrant_client.AsyncQdrantClient` (not the synchronous `QdrantClient`). Collection setup, `get()`, and `put()` SHALL be `async` and awaited by callers, so no cache operation blocks the event loop of an async service. Collection initialization SHALL NOT perform network I/O in the constructor; it SHALL occur in an explicit async initialization step invoked during the FastAPI `lifespan()` startup. All cache failures SHALL remain non-fatal (logged and treated as a cache miss / skipped write), preserving existing fail-open cache semantics.

#### Scenario: Cache lookup during request handling
- **WHEN** the orchestrator performs a semantic cache lookup while handling concurrent requests
- **THEN** the lookup is awaited asynchronously and does not block the event loop for other in-flight requests

#### Scenario: Service startup initializes cache collection
- **WHEN** the orchestrator starts and `SemanticCache` initializes during `lifespan()`
- **THEN** the collection existence check and creation are awaited asynchronously without stalling startup of the event loop

#### Scenario: Qdrant unavailable during cache operation
- **WHEN** a cache `get()` or `put()` raises an exception (e.g., Qdrant unreachable)
- **THEN** the error is logged, `get()` returns a miss (None), `put()` is skipped, and request handling continues normally

## ADDED Requirements

### Requirement: Knowledge service codebase is free of legacy ChromaDB code and dependencies
The Knowledge Service codebase SHALL use Qdrant as its sole vector database. `BGEEmbedder` in `services/knowledge/embedder.py` SHALL NOT inherit from ChromaDB interfaces or import `chromadb`. The `chromadb` library SHALL be removed from `services/knowledge/requirements.txt`. Unused environment variables (e.g. `CHROMA_PERSIST_DIR`) and docker volumes for ChromaDB SHALL be removed.

#### Scenario: BGEEmbedder instantiated without ChromaDB
- **WHEN** `BGEEmbedder` is initialized in the Knowledge Service
- **THEN** it wraps `HuggingFaceEmbeddings` directly without importing or referencing `chromadb`

### Requirement: Knowledge retriever supports hybrid vector and sparse search
The `KnowledgeRetriever` in `services/knowledge/retriever.py` SHALL implement hybrid vector + sparse search using `AsyncQdrantClient` query prefetching and RRF (Reciprocal Rank Fusion) fusion.

#### Scenario: Hybrid search query execution
- **WHEN** a retrieval request is submitted to `KnowledgeRetriever.retrieve()`
- **THEN** dense vector and sparse keyword scores are combined via RRF fusion to produce final relevance rankings
