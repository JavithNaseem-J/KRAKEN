# orchestrator-concurrency-control Specification

## Purpose
Delta spec for non-blocking embedding offload and episodic memory score resolution.

## Requirements

### Requirement: CPU-bound model embedding offloaded to async thread
Calls to `BGEEmbedder.embed_query` and `embed_documents` in `services/knowledge/retriever.py` and `services/memory/long_term.py` SHALL be executed using `asyncio.to_thread(...)` (or `loop.run_in_executor`) to prevent blocking the main asyncio event loop during vector calculation.

#### Scenario: Retrieval under high request rate
- **WHEN** multiple concurrent requests call `retriever.retrieve(...)` or `memory.search(...)`
- **THEN** embedding calculation runs off-thread and does not stall concurrent event loop I/O

### Requirement: Episodic memory retrieval parses similarity score correctly
The `retriever_node` in `services/orchestrator/graph/nodes/retriever.py` SHALL parse the `similarity` field from episodic memory search responses (`ep.get("similarity", 0.8)`) rather than looking for a non-existent `score` field.

#### Scenario: Episodic memory returned with similarity score
- **WHEN** episodic memory search returns records with `"similarity": 0.94`
- **THEN** `retriever_node` assigns `relevance_score = 0.94` to the resulting chunk
