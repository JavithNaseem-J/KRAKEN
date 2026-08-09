## ADDED Requirements

### Requirement: Service Dockerfiles Standardized
All 6 microservice Dockerfiles MUST use UTF-8 encoding and follow a consistent multi-stage build pattern using `python:3.11-slim`.

#### Scenario: Dockerfile build execution
- **WHEN** any service container is built with `docker build`
- **THEN** the build succeeds without character encoding warnings or missing dependencies.
