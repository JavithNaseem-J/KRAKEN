# readme-and-onboarding Specification

## Purpose
Root README and developer onboarding documentation.

## Requirements
### Requirement: README exists at repo root
A `README.md` SHALL exist at the repository root and SHALL include: project overview, prerequisites (Python 3.12, Docker Compose, a Groq API key), quickstart (5-command sequence from clone to running agent), link to `docs/architecture.md`, and a CI badge linking to the GitHub Actions workflow.

#### Scenario: README is discoverable on GitHub
- **WHEN** a user navigates to the repository root on GitHub
- **THEN** the README.md SHALL be rendered automatically with the above sections visible

#### Scenario: Quickstart commands are correct
- **WHEN** a developer follows the quickstart exactly on a fresh machine with Docker running
- **THEN** the system SHALL start all services, ingest knowledge, and render the React frontend UI at `http://localhost:5173` within the documented number of steps

#### Scenario: Architecture link is valid
- **WHEN** a user clicks the architecture link in the README
- **THEN** they SHALL be taken to `docs/architecture.md` (which exists and is committed)
