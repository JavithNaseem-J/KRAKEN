## ADDED Requirements

### Requirement: Multi-Action Selection
The Decider node SHALL support selecting multiple actions in a single turn when multiple independent operations are requested.

#### Scenario: Selecting multiple safe actions
- **WHEN** user query requests multiple independent read/auto-respond operations
- **THEN** decider node populates state with an array of action decisions

### Requirement: Concurrent Safe Action Dispatch
The Executor node SHALL execute all `SAFE` risk actions concurrently using `asyncio.gather` while maintaining individual action error isolation.

#### Scenario: Dispatching multiple safe actions in parallel
- **WHEN** state contains multiple `SAFE` risk actions
- **THEN** executor node dispatches all safe actions concurrently via `asyncio.gather` and aggregates results

#### Scenario: Error isolation during parallel dispatch
- **WHEN** one safe action fails during parallel execution
- **THEN** sibling safe actions complete successfully and individual error is captured in action results
