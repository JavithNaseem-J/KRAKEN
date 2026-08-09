## ADDED Requirements

### Requirement: Multi-Step Plan Decomposition
The Orchestrator SHALL allow the agent to decompose a complex user query into a sequence of sub-goal steps and track execution progress across graph iterations.

#### Scenario: Decomposing a multi-intent request into sub-goals
- **WHEN** user submits a request requiring multiple sequential operations
- **THEN** decider node outputs a multi-step plan array in state and begins executing step 1

### Requirement: Iterative Execution Feedback Loop
The Orchestrator SHALL route graph state from `executor` back to `reasoner` when unexecuted plan steps remain, adjusting subsequent steps based on intermediate tool outcomes.

#### Scenario: Routing back to reasoner for step 2
- **WHEN** step 1 execution finishes and unexecuted plan steps remain under the maximum step limit
- **THEN** graph conditional edge routes back to reasoner node with updated state and intermediate action results

#### Scenario: Terminating graph when plan completes
- **WHEN** all plan steps are completed or maximum step limit is reached
- **THEN** graph conditional edge routes to responder node to compose final answer
