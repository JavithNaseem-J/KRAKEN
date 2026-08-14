# sse-streaming Specification

## Purpose
TBD - created by archiving change kraken-production-polish. Update Purpose after archive.
## Requirements
### Requirement: Agent execution steps stream to the browser in real time
The system SHALL expose a `GET /v1/run/stream` SSE endpoint that emits one event per LangGraph node execution step, including node name, status (`start`/`end`), and elapsed milliseconds.

#### Scenario: Retriever step streams to UI
- **WHEN** the orchestrator begins the retriever node
- **THEN** the frontend receives an SSE event `{"node": "retriever", "status": "start"}` and displays a live badge "🔍 Retrieving knowledge..."

#### Scenario: Done event closes the stream
- **WHEN** the graph finishes execution
- **THEN** the server sends a final `{"node": "done", "response": {...}}` event and closes the SSE connection

#### Scenario: SSE connection kept alive on Render free tier
- **WHEN** 15 seconds elapse without a node event
- **THEN** the server sends a `: ping` SSE comment to prevent connection timeout

