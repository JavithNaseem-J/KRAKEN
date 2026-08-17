## ADDED Requirements

### Requirement: Lean AI Agent Dependencies & Single Observability
The AI Agent application SHALL rely exclusively on `src/` modules and Langfuse for observability, without requiring OpenTelemetry, Ragas, Datasets, or ReportLab dependencies.

#### Scenario: Running AI Agent backend server
- **WHEN** application boots via `python main.py` or unit tests run via `pytest`
- **THEN** server initializes cleanly without OpenTelemetry background export threads or HuggingFace dataset dependencies, exporting telemetry strictly to Langfuse.
