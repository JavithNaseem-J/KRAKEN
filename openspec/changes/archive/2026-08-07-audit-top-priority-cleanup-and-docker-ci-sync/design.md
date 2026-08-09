## Context

The audit identified critical misalignment: the repository deploys a deprecated Streamlit app (`frontend/app.py`) via Docker and Render, while the production React app (`frontend-react/`) lacks a Dockerfile, Compose entry, Render service configuration, and CI build pipeline. Additionally, dead components, stale egg-info directories, unused executor instances, and duplicated graph builders exist in the backend.

## Goals / Non-Goals

**Goals:**

- Remove `frontend/app.py` and `frontend/Dockerfile`.
- Create `frontend-react/Dockerfile` using multi-stage Node 20 build + Nginx alpine static serving.
- Update `docker-compose.yml`, `docker-compose.prod.yml`, and `render.yaml` to point to `frontend-react/Dockerfile`.
- Add a `frontend-react-ci` job in `.github/workflows/ci.yml` running `npm ci` and `npm run build`.
- Remove dead components `ChatInput.tsx` and `UserRoleSwitcher.tsx` from `frontend-react/src/components/`.
- Remove stale `akea_shared.egg-info/` and `kraken_shared.egg-info/` directories.
- Remove unused `ThreadPoolExecutor` from `services/orchestrator/main.py`.
- Refactor `build_graph` and `build_graph_async` in `services/orchestrator/graph/agent_graph.py` to call `_create_graph_builder()`.

**Non-Goals:**

- Changing frontend UI styling or backend API routes.

## Decisions

- **Decision 1**: `frontend-react/Dockerfile` uses multi-stage Node 20 build producing static assets served by Nginx on port 80.
- **Decision 2**: `_create_graph_builder()` in `agent_graph.py` encapsulates node and edge registration, returning uncompiled `StateGraph`.

## Risks / Trade-offs

- None identified.
