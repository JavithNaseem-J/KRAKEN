## ADDED Requirements

### Requirement: Centralized Qdrant collection initialization
The system SHALL provide `ensure_collection(client, collection_name, vector_size)` in `services/knowledge/ingest.py` to encapsulate checking and creating Qdrant vector store collections.

#### Scenario: Lifespan and ingest reuse collection creation helper
- **WHEN** `knowledge/main.py` (lifespan) or `knowledge/ingest.py` initializes vector store collections
- **THEN** both invoke `ensure_collection()` rather than duplicating `collection_exists` and `create_collection` logic
