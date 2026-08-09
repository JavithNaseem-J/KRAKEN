## REMOVED Requirements

### Requirement: Single-Layer Semantic Query Cache
**Reason**: The ChromaDB `akea_query_cache` collection has a correctness bug (stale results served after re-ingest because the cache is never invalidated), uses the wrong backend (vector-store metadata is not designed for caching), grows unboundedly (no TTL or eviction), and provides no measurable speedup for a corpus of ~55 documents that Chroma answers in under 5ms. The complexity and correctness cost outweighs any theoretical latency benefit at current scale.
**Migration**: Delete the `akea_query_cache` collection creation from `knowledge/main.py`. Remove the cache lookup block (lines 119–160) and the cache write block (lines 190–218) from `retriever.py`. No callers depend on the cache being present; the retriever's public interface (`retrieve()`) is unchanged.

### Requirement: Cache metadata length truncation guardrail
**Reason**: This requirement existed only to work around the ChromaDB metadata size limit imposed by the cache design being removed above. With no cache, the guardrail has no purpose.
**Migration**: No migration required; the while-loop truncation code is deleted along with the cache.

## ADDED Requirements

### Requirement: No semantic query cache in the knowledge retriever
The Knowledge Service retriever SHALL NOT maintain a semantic query cache. Every call to `retrieve()` SHALL perform a live ChromaDB query against the knowledge collections. The `akea_query_cache` collection SHALL NOT be created at service startup.

#### Scenario: Retrieve returns live results
- **WHEN** the same query is issued twice in sequence
- **THEN** both calls result in a fresh ChromaDB query; no cached result is served

#### Scenario: Re-ingest produces fresh results immediately
- **WHEN** knowledge documents are re-ingested via POST /ingest
- **THEN** the next retrieve call returns results reflecting the updated knowledge base (no stale cache entry can interfere)
