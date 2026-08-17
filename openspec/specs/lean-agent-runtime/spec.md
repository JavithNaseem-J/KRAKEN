# lean-agent-runtime Specification

## Purpose
Streamlined AI Agent application runtime relying exclusively on src/ modules and single Langfuse observability without legacy microservice scaffolding.

## Requirements

### Requirement: Lean AI Agent Dependencies & Single Observability
The AI Agent application SHALL rely exclusively on `src/` modules and Langfuse for observability, without requiring OpenTelemetry, Ragas, Datasets, or ReportLab dependencies.

#### Scenario: Running AI Agent backend server
- **WHEN** application boots via `python main.py` or unit tests run via `pytest`
- **THEN** server initializes cleanly without OpenTelemetry background export threads or HuggingFace dataset dependencies, exporting telemetry strictly to Langfuse.

### Requirement: No legacy microservice scaffolding in tracked content
The tracked repository SHALL contain no references to the removed `services/` and `shared/` packages: no Python import of `services.*` or `shared.*`, no build/deploy artifact copying or building those directories, and no Makefile/pyproject target operating on them. The legacy `services/` and `shared/` deletions SHALL be committed so that `git ls-files` contains no path under either directory. The OpenTelemetry import and instrumentation block in `src/api/orchestrator.py` SHALL be removed, leaving Langfuse as the only observability integration.

#### Scenario: Repository imports resolve from src only
- **WHEN** a static scan runs for `from services`, `import services`, `from shared`, `import shared` across tracked `.py` files
- **THEN** zero matches are found

#### Scenario: Build artifacts target the monolith
- **WHEN** the Dockerfile, compose files, render.yaml, Makefile, and pyproject.toml are inspected
- **THEN** none references `services/` or `shared/` paths, and `pip install -e .` installs the `src`-based application package

#### Scenario: Orchestrator has no OpenTelemetry code
- **WHEN** `src/api/orchestrator.py` is inspected
- **THEN** it contains no `opentelemetry` imports, tracer provider setup, or instrumentor calls, and the application boots and serves requests with Langfuse-only observability
