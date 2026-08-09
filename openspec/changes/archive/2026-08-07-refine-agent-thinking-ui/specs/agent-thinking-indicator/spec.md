# agent-thinking-indicator Specification

## ADDED Requirements

### Requirement: Inline Agent Thinking Indicator
The system MUST render a compact inline thinking badge (`🧠 Agent is thinking…`) while the agent is executing queries.

#### Scenario: Streaming response state
- **WHEN** the agent is processing a query
- **THEN** the streaming loading indicator displays `🧠 Agent is thinking…`

### Requirement: Input Disabled Placeholder
The system MUST update the chat input textarea disabled placeholder to `Agent is thinking…` while busy.

#### Scenario: Disabled textarea during agent execution
- **WHEN** the chat input is disabled due to active agent processing
- **THEN** the placeholder text displays `Agent is thinking…`
