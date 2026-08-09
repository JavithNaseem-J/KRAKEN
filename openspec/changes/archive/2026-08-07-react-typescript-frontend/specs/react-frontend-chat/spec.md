# react-frontend-chat Specification

## ADDED Requirements

### Requirement: React SPA Chat Interface
The system MUST provide a Vite + React + TypeScript single-page application replacing the Streamlit interface.

#### Scenario: Submitting a helpdesk query
- **WHEN** a user enters a query in the chat input
- **THEN** the React app sends a `POST /v1/run` HTTP request to Gateway using the configured `X-API-Key`

### Requirement: Background Status Polling
The system MUST automatically poll the Gateway API when an action is in `pending_approval` state until execution completes.

#### Scenario: Polling pending approval state
- **WHEN** the response status is `pending_approval`
- **THEN** the app polls `POST /v1/run` every 3 seconds until status is `completed`
