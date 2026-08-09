## Why

A comprehensive audit revealed key structural debt and missing production basics: `frontend/app.py` (deprecated Streamlit app) is still built by Docker and Render while `frontend-react` is omitted, `frontend-react` lacks CI testing, `ChatInput.tsx` and `UserRoleSwitcher.tsx` are unreferenced dead code, `ThreadPoolExecutor` in `orchestrator/main.py` is unused, and `agent_graph.py` contains duplicated graph builder logic. Resolving these top-priority items aligns Docker, Render, CI, and codebase structure with production standards.

## What Changes

- Delete deprecated Streamlit application files (`frontend/app.py`, `frontend/Dockerfile`).
- Delete unused dead React components (`frontend-react/src/components/ChatInput.tsx`, `frontend-react/src/components/UserRoleSwitcher.tsx`).
- Delete stale build metadata directories (`akea_shared.egg-info/`, `kraken_shared.egg-info/`).
- Create `frontend-react/Dockerfile` (Nginx multi-stage build) and update `docker-compose.yml`, `docker-compose.prod.yml`, and `render.yaml` to deploy `frontend-react`.
- Add `frontend-react` build, type checking (`tsc -b`), and test steps to `.github/workflows/ci.yml`.
- Remove unused `ThreadPoolExecutor` from `services/orchestrator/main.py`.
- Refactor `build_graph` and `build_graph_async` in `services/orchestrator/graph/agent_graph.py` to share a single internal graph builder helper.

## Capabilities

### New Capabilities

- `react-frontend-containerization-and-ci`: Containerizes `frontend-react` with Nginx, wires it into Docker Compose and Render, and enforces `frontend-react` type checking and build checks in CI.
- `orchestrator-graph-deduplication`: Refactors agent graph construction to eliminate duplicated node/edge definitions and removes dead executor resources.

### Modified Capabilities

None.

## Impact

- `frontend/`: Directory removed.
- `frontend-react/Dockerfile`: Created.
- `frontend-react/src/components/`: Unused `ChatInput.tsx` and `UserRoleSwitcher.tsx` deleted.
- `docker-compose.yml`, `docker-compose.prod.yml`, `render.yaml`: Updated frontend service to `frontend-react`.
- `.github/workflows/ci.yml`: Added React build & type check job.
- `services/orchestrator/main.py`: Removed dead `ThreadPoolExecutor`.
- `services/orchestrator/graph/agent_graph.py`: Refactored graph builder functions.
