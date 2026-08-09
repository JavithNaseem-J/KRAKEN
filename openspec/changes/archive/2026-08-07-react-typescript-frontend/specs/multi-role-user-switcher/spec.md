# multi-role-user-switcher Specification

## ADDED Requirements

### Requirement: Sidebar Role Selection
The system MUST provide a user identity selector in the sidebar allowing instant switching between predefined security roles (`Alice` [Analyst], `Bob` [Security Lead], `Admin` [Approver]).

#### Scenario: Switching active user role
- **WHEN** the user selects `Bob` from the role dropdown
- **THEN** subsequent `POST /v1/run` requests include `user_id: "bob"`
