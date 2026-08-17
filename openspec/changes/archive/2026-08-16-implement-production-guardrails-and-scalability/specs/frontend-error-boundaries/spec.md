## ADDED Requirements

### Requirement: React Error Boundary Protection for UI Stream Drawers
The frontend React application SHALL isolate stream rendering and drawer component failures within a React Error Boundary component.

#### Scenario: Rendering exception inside Telemetry or Reasoning drawer
- **WHEN** unhandled rendering error occurs inside `TelemetryDrawer` or `ReasoningInspectorDrawer`
- **THEN** Error Boundary catches exception, displays inline error fallback card, and prevents entire React UI crash.
