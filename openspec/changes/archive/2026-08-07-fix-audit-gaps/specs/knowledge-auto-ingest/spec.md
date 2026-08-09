## ADDED Requirements

### Requirement: Automatic Ingestion on Empty Collection
The Knowledge service SHALL check collection point count during startup lifespan and automatically ingest domain files if the collection is empty.

#### Scenario: Booting knowledge service with empty collection
- **WHEN** knowledge service starts up and detects 0 points in Qdrant collection
- **THEN** it automatically triggers batch knowledge ingestion for FAQ, SLA, and Ticket files before receiving queries
