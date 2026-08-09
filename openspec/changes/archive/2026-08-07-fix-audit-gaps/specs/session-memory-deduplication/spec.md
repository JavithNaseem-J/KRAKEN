## ADDED Requirements

### Requirement: Session Turn Deduplication
The Memory Writer node SHALL persist only newly generated messages for the current turn to the short-term session memory service, avoiding duplicate historical entries in Redis.

#### Scenario: Appending current turn messages without history duplication
- **WHEN** memory writer node executes at the end of a query run
- **THEN** it sends only newly generated turn messages to the session memory append endpoint
