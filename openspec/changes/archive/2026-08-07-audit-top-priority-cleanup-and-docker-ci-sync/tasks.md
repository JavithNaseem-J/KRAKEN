## 1. Top-Priority Codebase Cleanup & Docker/CI Alignment

- [x] 1.1 Remove deprecated Streamlit frontend files (`frontend/app.py`, `frontend/Dockerfile`) and dead React components (`ChatInput.tsx`, `UserRoleSwitcher.tsx`)
- [x] 1.2 Remove stale egg-info directories (`akea_shared.egg-info/`, `kraken_shared.egg-info/`) and update `.gitignore`
- [x] 1.3 Create `frontend-react/Dockerfile` (Nginx multi-stage build) and update `docker-compose.yml`, `docker-compose.prod.yml`, and `render.yaml` to deploy `frontend-react`
- [x] 1.4 Add `frontend-react` build and type check jobs to `.github/workflows/ci.yml`
- [x] 1.5 Remove dead `ThreadPoolExecutor` in `services/orchestrator/main.py` and refactor `build_graph`/`build_graph_async` in `services/orchestrator/graph/agent_graph.py`
- [x] 1.6 Verify Vite build, Python unit tests (`pytest`), and validate change
