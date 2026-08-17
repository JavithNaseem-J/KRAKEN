## MODIFIED Requirements

### Requirement: CI pipeline installs full dependency stack and verifies components
The GitHub Actions workflow in `.github/workflows/ci.yml` SHALL install the consolidated dependency stack (via `uv sync --frozen` from `pyproject.toml`/`uv.lock`, with runtime and dev/eval extras) before running linting (`ruff check`), static type checking (`mypy src/`), unit tests, and the integration suite (`pytest tests/integration -m integration`). CI SHALL include a frontend validation step (`npm run lint` and `npm run build` in `frontend-react/`) and a Docker build + smoke check step that builds the single consolidated application image and verifies `/health`.

#### Scenario: CI pipeline runs unit tests cleanly
- **WHEN** CI executes `pytest tests/unit`
- **THEN** all tests run without `ModuleNotFoundError` for missing FastAPI, LangChain, Qdrant, or Redis packages and without import errors referencing removed `services.*` or `shared.*` modules

#### Scenario: CI integration gate runs the consolidated app
- **WHEN** CI executes `pytest tests/integration -m integration`
- **THEN** the consolidated application boots with real lifespans inside the test process and the end-to-end HITL flow passes with no external services

#### Scenario: CI frontend build check
- **WHEN** CI runs the frontend step
- **THEN** `npm run lint` and `npm run build` in `frontend-react/` succeed with zero TypeScript, lint, or bundling errors

#### Scenario: CI Docker container smoke check
- **WHEN** CI runs container smoke validation
- **THEN** `docker compose up --build -d` completes using the single-application image and the gateway `/health` endpoint returns HTTP 200 OK
