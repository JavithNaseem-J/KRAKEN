# ci-workflow Specification

## Purpose
Continuous Integration pipeline with automated linting, type-checking, unit testing, and container configuration validation.

## Requirements

### Requirement: GitHub Actions CI workflow
A `.github/workflows/ci.yml` pipeline SHALL exist that executes `ruff check .`, `mypy shared/ services/`, `pytest tests/ -v`, and a Docker Compose startup health validation on pushes and pull requests.

#### Scenario: CI pipeline runs on pull request
- **WHEN** code is pushed to a branch or pull request opened
- **THEN** GitHub Actions runs linting, static type checking, unit tests, and container health verification
