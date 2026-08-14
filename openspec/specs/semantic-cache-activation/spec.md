# semantic-cache-activation Specification

## Purpose
TBD - created by archiving change codebase-health-remediation. Update Purpose after archive.
## Requirements
### Requirement: SemanticCache.put() is called after successful /run completion
The orchestrator's `/run` endpoint SHALL call `SemanticCache.put(query_vector, query_text, response_dict)` after a successful graph execution, before returning the response. The put call SHALL be non-blocking (wrapped in `asyncio.create_task()`) and fail-open.

#### Scenario: Successful query populates cache
- **WHEN** the orchestrator completes a `/run` request successfully with `semantic_cache_enabled=True`
- **THEN** `SemanticCache.put()` is called with the query vector, query text, and response payload

#### Scenario: Subsequent identical query returns cache hit
- **WHEN** the orchestrator receives a query with cosine similarity ≥ 0.92 to a previously cached query
- **THEN** the cached response is returned without re-executing the LangGraph agent

#### Scenario: Cache put failure does not affect response
- **WHEN** `SemanticCache.put()` raises an exception (e.g., Qdrant unreachable)
- **THEN** the original response is still returned to the caller and the error is logged

