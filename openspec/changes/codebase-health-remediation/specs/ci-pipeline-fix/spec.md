## ADDED Requirements

### Requirement: CI pipeline installs full dependency stack and verifies components
The GitHub Actions workflow in `.github/workflows/ci.yml` SHALL install all required production and dev dependencies (`requirements.txt`, `requirements-dev.txt`, per-service requirements) before running linting, static type checking, and unit tests. CI SHALL include a frontend build validation step (`npm run build` in `frontend-react/`) and a Docker Compose build + smoke check step.

#### Scenario: CI pipeline runs unit tests cleanly
- **WHEN** CI executes `pytest tests/`
- **THEN** all tests run without `ModuleNotFoundError` for missing FastAPI, LangChain, Qdrant, or Redis packages

#### Scenario: CI frontend build check
- **WHEN** CI runs the frontend step
- **THEN** `npm run build` in `frontend-react/` succeeds with zero TypeScript or bundling errors

#### Scenario: CI Docker container smoke check
- **WHEN** CI runs container smoke validation
- **THEN** `docker compose up --build -d` completes and the gateway `/health` endpoint returns HTTP 200 OK
