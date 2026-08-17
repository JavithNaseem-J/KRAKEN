## Why

The current KRAKEN codebase spreads logic across 7 separate microservice folders under `services/` and a top-level `shared/` package. Reorganizing the project into a single, standardized AI Agent layout under `src/` (`src/agent/`, `src/tools/`, `src/models/`, `src/prompts/`, `src/utils/`, `src/api/`) with a root `main.py` entrypoint simplifies architecture, eliminates inter-service HTTP latency during local runs, and aligns with standard AI Agent project design conventions.

## What Changes

- **Root Structure**: Create top-level `src/`, `data/`, `logs/`, `tests/`, and root `main.py` entrypoint.
- **Agent Package (`src/agent/`)**: Consolidate core agent execution loop, state management, and graph nodes into `agent.py`, `executor.py`, `state.py`, and `memory.py`.
- **Tools Package (`src/tools/`)**: Consolidate action definitions and tool functions (ticket handler, system commands, vector search) into `src/tools/`.
- **Models Package (`src/models/`)**: Move LLM client abstractions, provider switching, and embedding client setups into `src/models/` (`llm_client.py`, `embeddings.py`).
- **Prompts Package (`src/prompts/`)**: Move system instructions and prompt templates into `src/prompts/` (`system_prompts.py`, `agent_prompts.py`).
- **Utils Package (`src/utils/`)**: Consolidate configuration management, logging, path validation, and security middleware into `src/utils/` (`config.py`, `logger.py`, `helpers.py`).
- **API Package (`src/api/`)**: Consolidate FastAPI gateway and endpoint routes into `src/api/` (`routes.py`, `schemas.py`).

## Capabilities

### New Capabilities

- `standard-agent-structure`: Consolidated AI Agent directory architecture matching standard `src/` layout.

### Modified Capabilities

*No existing spec requirements are changing.*

## Impact

- **Affected Folders**: Move/refactor `services/` and `shared/` into `src/` and `main.py`.
- **Imports**: Update all internal module import statements across Python codebase and unit tests.
