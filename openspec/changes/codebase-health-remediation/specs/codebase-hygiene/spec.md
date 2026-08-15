## ADDED Requirements

### Requirement: General Codebase Hygiene
The repository SHALL adhere to standard Python and repository hygiene guidelines:
- All `shared/` subpackages (`shared/middleware/`, `shared/models/`, `shared/db/`) SHALL contain `__init__.py` files.
- `ruff check .` SHALL pass with zero violations.
- Obsolete files (`migrations/`, `alembic.ini`, `.agent/`, `scripts/run_security_audit.py`, `public/_redirects`) SHALL be removed.
- `.env.example` SHALL use placeholder hostnames (`your-project.supabase.co`) and omit unused keys.
- Unused parameters, unused top-level imports, and unreachable logic branches SHALL be removed across all services.

#### Scenario: CI ruff linting gate
- **WHEN** `ruff check .` is executed in CI
- **THEN** it completes with 0 errors and 0 warnings

#### Scenario: Package discovery for subpackages
- **WHEN** `shared` is imported or installed as a package
- **THEN** all submodules under `shared.middleware`, `shared.models`, and `shared.db` are importable as standard Python packages
