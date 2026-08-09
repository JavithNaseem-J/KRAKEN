# llm-observability Specification

## ADDED Requirements

### Requirement: Langfuse callback handler initialization
The Orchestrator Service SHALL inspect `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` during startup. If valid keys are provided, it SHALL construct a `langfuse.callback.CallbackHandler` and pass it to LangGraph execution calls. If keys are missing, it SHALL run gracefully without registering callbacks.

#### Scenario: Langfuse enabled with valid keys
- **WHEN** the Orchestrator executes `/run` and `LANGFUSE_PUBLIC_KEY` is configured
- **THEN** it SHALL stream trace spans, token counts, and node execution latency to Langfuse

#### Scenario: Graceful fallback when Langfuse keys are omitted
- **WHEN** the Orchestrator executes `/run` and `LANGFUSE_PUBLIC_KEY` is empty
- **THEN** it SHALL execute the agent graph normally without throwing authentication or network errors
