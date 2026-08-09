## ADDED Requirements

### Requirement: Async Checkpointer Reaper Resumption
The Orchestrator background reaper loop SHALL invoke the graph using async `ainvoke` when resuming timed-out HITL approvals to ensure compatibility with `AsyncPostgresSaver`.

#### Scenario: Resuming timed-out HITL approval asynchronously
- **WHEN** background reaper loop identifies an expired HITL approval
- **THEN** it executes `await app.state.agent_graph.ainvoke(Command(resume={"decision": "timeout"}), config)` without crashing or raising checkpointer exceptions
