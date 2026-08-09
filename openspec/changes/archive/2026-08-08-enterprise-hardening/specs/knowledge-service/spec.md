## ADDED Requirements

### Requirement: Strict Pydantic Ingestion Contract Validation
The Knowledge ingestion service SHALL validate all raw document records against strict Pydantic schemas prior to chunking and upserting points to Qdrant Cloud.

#### Scenario: Valid ticket ingestion
- **WHEN** raw ticket JSON records are loaded from disk
- **THEN** the system validates `ticket_id`, `subject`, `status`, and `priority` fields against `TicketDocument` Pydantic model before vectorization

### Requirement: Normalized Composite RAG Scoring
The Knowledge retriever SHALL normalize composite RRF rank scores and blend them with raw Qdrant vector cosine similarity to return relevance scores bounded strictly between 0.0 and 1.0.

#### Scenario: Retrieval score normalization
- **WHEN** a user query is executed against Qdrant Cloud and sparse keyword indices
- **THEN** the retriever outputs a normalized composite relevance score between 0.0000 and 1.0000 for each retrieved chunk
