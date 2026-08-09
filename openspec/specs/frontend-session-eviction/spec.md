# frontend-session-eviction Specification

## Purpose
Browser storage quota management via LRU session eviction in React frontend.

## Requirements

### Requirement: Frontend session LRU eviction
The React frontend (`frontend-react/src/App.tsx`) SHALL enforce an upper limit of 20 stored chat sessions in `localStorage`, evicting the oldest sessions by `updated_at` timestamp whenever new sessions exceed the threshold.

#### Scenario: Sessions exceed 20 limit
- **WHEN** a user creates a 21st chat session
- **THEN** the oldest session is removed from `localStorage` before saving the updated list
