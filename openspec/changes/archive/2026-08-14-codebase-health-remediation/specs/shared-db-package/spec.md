## ADDED Requirements

### Requirement: shared.db is a proper Python package
The `shared/db/` directory SHALL be a Python package with an `__init__.py` that re-exports `create_pool` from `shared/db/pool.py` and ticket helpers from `shared/db/tickets.py`. The file `shared/db.py` SHALL NOT exist alongside the `shared/db/` directory.

#### Scenario: Import shared.db.tickets succeeds
- **WHEN** any service imports `from shared.db.tickets import create_tickets_table`
- **THEN** the import succeeds without `ModuleNotFoundError`

#### Scenario: Import shared.db.create_pool backward compatibility
- **WHEN** any service imports `from shared.db import create_pool`
- **THEN** the import succeeds via the `__init__.py` re-export

#### Scenario: setuptools discovers shared.db package
- **WHEN** `setuptools.packages.find()` scans the `shared/` directory
- **THEN** `shared.db` is included in the discovered packages because `__init__.py` exists
