## Context

The KRAKEN repository is transitioning from multi-folder microservices under `services/` into a standardized single-agent directory layout under `src/`.

## Goals / Non-Goals

**Goals:**
- Reorganize all Python backend modules under `src/` (`agent/`, `tools/`, `models/`, `prompts/`, `utils/`, `api/`).
- Provide root `main.py` entrypoint.
- Maintain full feature parity, test coverage, and React frontend compatibility.

**Non-Goals:**
- Changing frontend UI components or breaking API contracts.

## Decisions

### Decision 1: Target Module Mapping
- `src/agent/`: `agent.py` (graph builder), `executor.py` (action execution node), `state.py` (GraphState), `memory.py` (memory writer node).
- `src/tools/`: Action definitions, ticket handler, vector search tool.
- `src/models/`: `llm_client.py` (LangChain/LLM initialization), `embeddings.py` (embeddings setup).
- `src/prompts/`: `system_prompts.py`, `agent_prompts.py`.
- `src/utils/`: `config.py` (Pydantic Settings), `logger.py` (structlog setup), `helpers.py` (path validation & auth).
- `src/api/`: `routes.py` (FastAPI app and route definitions), `schemas.py` (Pydantic request/response models).
- `main.py`: Root entrypoint starting Uvicorn server on port 8000.

## Risks / Trade-offs

- **[Risk] Broken Imports**: Internal module imports changing across 185 unit tests.
  - *Mitigation*: Update import paths across `tests/unit/` systematically.
