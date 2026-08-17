## Why

Per user instruction, we are removing three specific components to streamline the codebase and eliminate dead weight:
1. **OpenTelemetry (`opentelemetry-*`)**: Redundant observability layer. Langfuse provides full LLM generation tracing, token costs, prompt tracking, and node execution latencies natively.
2. **pgvector (`pgvector`)**: Redundant secondary vector database extension. KRAKEN standardizes on **Qdrant** as the primary high-performance vector store.
3. **Legacy Microservice Directories (`services/` & `shared/`)**: Dead code remaining after moving all active backend code into `src/` (`src/agent`, `src/tools`, `src/models`, `src/prompts`, `src/utils`, `src/api`) and root `main.py`.

## What Changes

- **Dependencies (`requirements.txt`)**: Remove `opentelemetry-*` and `pgvector`.
- **Observability (`src/utils/`)**: Remove OpenTelemetry exporter setups and standardize 100% on Langfuse for LLM & agent tracing.
- **Legacy Directory Cleanup**: Delete obsolete legacy `services/` and `shared/` microservice folders.

## Capabilities

### New Capabilities

- `lean-agent-runtime`: Lightweight, zero-bloat runtime environment powered strictly by `src/` and Langfuse observability.

## Impact

- **Performance & Footprint**: Faster startup, zero background OpenTelemetry export threads.
- **Maintainability**: Single unified source directory (`src/`), zero legacy microservices duplicate code.
