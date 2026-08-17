## ADDED Requirements

### Requirement: Modular LangGraph State Graph and Node Dispatch
The Orchestrator service SHALL organize LangGraph nodes, state definitions, prompt templates, and routing logic into decoupled modules under `services/orchestrator/graph/` and `services/orchestrator/prompts.py`.

#### Scenario: Orchestrator routes query through agent state graph
- **WHEN** user query enters orchestrator graph execution loop
- **THEN** state graph dispatches execution cleanly to specialized node modules without inline monolithic handlers.

### Requirement: Decoupled Telemetry Tracing and Observability
The Orchestrator service SHALL handle telemetry collection and OpenTelemetry trace context formatting in `services/orchestrator/telemetry.py`.

#### Scenario: Agent graph emits execution telemetry
- **WHEN** graph node completes execution step
- **THEN** telemetry module records step duration, state transition, and LLM token metadata cleanly.
