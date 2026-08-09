# suggestion-pills-manual-send Specification

## ADDED Requirements

### Requirement: Suggestion Pill Input Population
The system MUST populate the input textarea and focus it when a suggestion pill is clicked, without triggering query execution until the user manually sends the message.

#### Scenario: Clicking a suggestion pill
- **WHEN** a user clicks any quick action suggestion pill
- **THEN** the input textarea is filled with the prompt text and focused, requiring an explicit Send action to execute.
