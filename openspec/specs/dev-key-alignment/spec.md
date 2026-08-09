# dev-key-alignment Specification

## Purpose
TBD - created by archiving change fix-low-severity-issues. Update Purpose after archive.
## Requirements
### Requirement: Unified Dev API Keys Across Codebase
All test scripts, evaluation tools, and client applications MUST default to `dev-key-alice-longer-secure-key` to ensure out-of-the-box compatibility with the Gateway service rate-limiting and authentication middleware.

#### Scenario: Frontend and CLI client requests
- **WHEN** `frontend/app.py`, `scripts/benchmark.py`, or `eval_harness.py` sends a request to the default Gateway setup
- **THEN** the request passes authentication without 401 Unauthorized errors.

