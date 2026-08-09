# kraken-brand-layout Specification

## ADDED Requirements

### Requirement: Single KRAKEN Brand Header
The system MUST display the project title **KRAKEN** in exactly one location: the top left of the left sidebar.

#### Scenario: Viewing enterprise brand header
- **WHEN** the application renders
- **THEN** the sidebar header displays **KRAKEN** and the main window header omits redundant project titles.

### Requirement: Top Right Header Cleanup
The system MUST omit duplicate active persona badges (`Admin · Approver`) from the top right corner.

#### Scenario: Top right status items
- **WHEN** the main header bar renders
- **THEN** top right items display live system health without duplicate persona pills.
