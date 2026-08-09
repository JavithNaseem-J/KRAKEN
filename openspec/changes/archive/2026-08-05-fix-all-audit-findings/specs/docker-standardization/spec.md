## ADDED Requirements

### Requirement: Render deployment specifications include health check probes and appropriate service tiers
In `render.yaml`, every web service entry SHALL declare a `healthCheckPath: /health` property. Critical services (including `akea-orchestrator` and `akea-approval`) SHALL specify `plan: starter` to prevent cold-start delays during Human-in-the-Loop workflows.

#### Scenario: Render routes traffic after health check passes
- **WHEN** a service deploys on Render
- **THEN** traffic is routed to the service instance only after its `/health` probe returns HTTP 200 OK

#### Scenario: HITL approval flow unaffected by cold start
- **WHEN** an approval callback is executed against the `akea-approval` service
- **THEN** the service is active on the `starter` plan and responds immediately without sleeping/cold-start latency
