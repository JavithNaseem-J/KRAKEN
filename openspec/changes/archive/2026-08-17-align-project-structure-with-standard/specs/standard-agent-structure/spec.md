## ADDED Requirements

### Requirement: Standard AI Agent Project Directory Layout
The repository SHALL organize all backend AI agent code under a unified `src/` directory structure with top-level `main.py` entrypoint.

#### Scenario: Running the AI Agent application
- **WHEN** user executes `python main.py` or runs Uvicorn on `src.api.routes:app`
- **THEN** application initializes configuration from `src.utils.config`, loads models from `src.models`, wires tools from `src.tools`, and serves API endpoints on `src.api`.
