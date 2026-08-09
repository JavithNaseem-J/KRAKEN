# reasoning-inspector-formatting Specification

## ADDED Requirements

### Requirement: Structured Reasoning Cards
The system MUST format step-by-step reasoning sections into clean callout cards inside the Reasoning Inspector drawer using Markdown rendering.

#### Scenario: Inspecting agent reasoning steps
- **WHEN** the user opens the Reasoning Inspector drawer for an assistant message
- **THEN** step-by-step reasoning sections render as structured cards without raw unparsed markdown symbols
