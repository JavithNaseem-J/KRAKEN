## ADDED Requirements

### Requirement: Graceful Formatting of Null Selected Actions
The Responder node SHALL handle queries where `selected_action` is `None` without outputting raw `"Action 'None' was selected"` string fragments.

#### Scenario: Synthesizing response when no action was selected
- **WHEN** decider node returns `selected_action: None` or decider fails
- **THEN** responder node omits action execution text and presents a clean factual or error explanation to the user
