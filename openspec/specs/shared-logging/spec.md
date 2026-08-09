# shared-logging Specification

## Purpose
TBD - created by archiving change fix-medium-severity-issues. Update Purpose after archive.
## Requirements
### Requirement: Centralized Logging Configuration
The system SHALL provide a shared `configure_logging()` function in `shared/logging.py` that configures structlog with `log_level` and `log_format` settings.

#### Scenario: Service Lifespan Configures Structlog
- **WHEN** any microservice starts up
- **THEN** it calls `configure_logging()` in its lifespan handler to apply uniform logging formatting.

