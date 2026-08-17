## 1. Directory & Package Migration

- [x] 1.1 Scaffold `src/` subdirectories (`agent/`, `tools/`, `models/`, `prompts/`, `utils/`, `api/`), `data/`, `logs/`.
- [x] 1.2 Migrate core agent graph and nodes to [`src/agent/`](file:///F:/DSML/KRAKEN/src/agent).
- [x] 1.3 Migrate action tools to [`src/tools/`](file:///F:/DSML/KRAKEN/src/tools).
- [x] 1.4 Migrate LLM client and embedding setup to [`src/models/`](file:///F:/DSML/KRAKEN/src/models).
- [x] 1.5 Migrate prompt templates to [`src/prompts/`](file:///F:/DSML/KRAKEN/src/prompts).
- [x] 1.6 Migrate shared utilities and config to [`src/utils/`](file:///F:/DSML/KRAKEN/src/utils).
- [x] 1.7 Migrate FastAPI routes and schemas to [`src/api/`](file:///F:/DSML/KRAKEN/src/api).
- [x] 1.8 Create root [`main.py`](file:///F:/DSML/KRAKEN/main.py) entrypoint.

## 2. Unit Test & Verification

- [x] 2.1 Update import paths in `tests/unit/`.
- [x] 2.2 Run full `pytest` test suite to verify 100% test pass rate.
