# knowledge-cache Specification

## Purpose
Delta spec for non-blocking Qdrant client usage, correct `/stats` point counting, and service-internal ingestion.

## Requirements

### Requirement: Stats endpoint awaits AsyncQdrantClient get_collection
The `GET /stats` endpoint in `services/knowledge/main.py` SHALL await `app.state.client.get_collection(...)` on the `AsyncQdrantClient` instance. Point counts SHALL be retrieved from `info.points_count` and returned accurately without raising `AttributeError` or returning silent 0 counts.

#### Scenario: Stats endpoint called on active collection
- **WHEN** `GET /stats` is requested
- **THEN** the endpoint awaits `get_collection`, extracts `points_count`, and returns `{"akea_knowledge": <actual_count>}` with HTTP 200 OK

### Requirement: Ingestion executes natively within service boundary
The `POST /ingest` endpoint in `services/knowledge/main.py` SHALL invoke an async ingestion helper in `services/knowledge/ingest.py` using `AsyncQdrantClient`. It SHALL NOT import functions from `scripts/ingest_knowledge.py` or depend on repo-root scripts outside the service container.

#### Scenario: Ingestion triggered via HTTP endpoint inside Docker
- **WHEN** `POST /ingest` is called with a valid service token inside a Docker container
- **THEN** the service loads chunks, awaits `AsyncQdrantClient.upsert(...)`, and returns actual ingested document counts
