## 1. Remove OpenTelemetry, pgvector, and Legacy Folders

- [x] 1.1 Remove `opentelemetry-*` and `pgvector` from [`requirements.txt`](file:///F:/DSML/KRAKEN/requirements.txt).
- [x] 1.2 Remove OpenTelemetry setup modules (`services/orchestrator/telemetry.py`) and references across `src/`.
- [x] 1.3 Delete legacy microservices folders (`services/`, `shared/`) and `kraken_shared.egg-info/`.

## 2. Verification

- [x] 2.1 Run full `pytest` test suite to verify 100% test pass rate.
- [x] 2.2 Run `npm run build` in `frontend-react` to verify clean production build.
