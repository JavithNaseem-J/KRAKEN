## ADDED Requirements

### Requirement: Single canonical copy of every module
Every module in the `src/` tree SHALL exist in exactly one canonical location. Duplicate copies of the same module (byte-identical or near-identical re-nestings under different packages) SHALL NOT be tracked. Package `__init__.py` files SHALL import only live modules and SHALL NOT keep dead duplicates importable.

#### Scenario: No duplicate module hashes in src
- **WHEN** all Python files under `src/` are hashed after normalizing blank lines
- **THEN** no two distinct module paths share the same content hash, excluding empty `__init__.py` files

#### Scenario: Tools package exports only live modules
- **WHEN** `src/tools/__init__.py` is imported
- **THEN** it exposes only the modules used by the action service (`ticket`, `write_tool`) and imports no duplicate handler copies

#### Scenario: Tests target canonical modules
- **WHEN** the unit test suite is collected
- **THEN** no test imports a module that has been designated a duplicate copy, and every previously duplicated module's behavior is covered through its canonical location

### Requirement: Dead stub modules are not tracked
Modules that return placeholder values, define unused functions, or are imported by nothing SHALL NOT be tracked. Specifically the following SHALL NOT exist: `src/tools/calculator.py`, `src/tools/search.py`, `src/models/embeddings.py`, `src/prompts/system_prompts.py`, `src/prompts/agent_prompts.py`, `src/api/schemas.py`, `src/utils/helpers.py`, `src/utils/logger.py`, and `src/observability.py`.

#### Scenario: Stub removal verified
- **WHEN** the repository tree is inspected
- **THEN** none of the listed stub files exist and `pytest` plus `ruff` pass without them
