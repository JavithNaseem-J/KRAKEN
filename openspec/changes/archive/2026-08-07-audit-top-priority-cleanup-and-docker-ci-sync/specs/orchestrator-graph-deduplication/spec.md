# orchestrator-graph-deduplication Specification

## ADDED Requirements

### Requirement: Single StateGraph Construction Pattern
The orchestrator MUST construct agent graphs from a single shared graph builder helper.

#### Scenario: Synchronous vs Asynchronous Checkpointer Compilation
- **WHEN** initializing orchestrator agent graphs
- **THEN** both `build_graph` and `build_graph_async` construct nodes and edges via `_create_graph_builder()`, differing only in checkpointer compilation.
