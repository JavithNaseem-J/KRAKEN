## ADDED Requirements

### Requirement: Multi-service status aggregator script
`scripts/check_health.py` SHALL query the health endpoints of all 7 services and print a consolidated status table.

#### Scenario: All services healthy
- **WHEN** `python scripts/check_health.py` is executed and all services are running
- **THEN** it outputs an HTTP status 200 and healthy indicator for all services and exits with code 0

#### Scenario: Service offline
- **WHEN** `python scripts/check_health.py` is executed and one or more services are unreachable
- **THEN** it highlights the failed service and exits with non-zero exit code
