## ADDED Requirements

### Requirement: Single-Layer Semantic Query Cache
The system SHALL rely on the Knowledge Service ChromaDB `akea_query_cache` for query caching, omitting redundant Redis exact-match query caching in the orchestrator.

#### Scenario: Semantic Knowledge Retrieval
- **WHEN** a user query is sent to the retriever node
- **THEN** it passes directly to the Knowledge Service which resolves exact or near-duplicate queries via its ChromaDB semantic cache collection.
