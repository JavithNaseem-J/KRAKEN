## Why

When the agent graph encounters a CRITICAL action interrupt, the SSE streaming endpoint (`/v1/run/stream`) completes without yielding a `response` object, causing the React frontend to execute fallback polling (`runAgentQuery('')`) against the interrupted thread. Furthermore, decider prompt keyword fallthrough misclassifies general questions containing words like "critical" or "vulnerabilities" as `escalate`. Together, these root causes cause every user prompt in a session to append duplicate plain-text "A CRITICAL triage action requires human approval" messages.

## What Changes

- **SSE Stream Interrupt Event**: Update `run_stream` in `services/orchestrator/main.py` to yield an explicit `pending_approval` SSE event when the graph pauses at an interrupt, ensuring `api.ts` receives `event.response`.
- **Decider Ticket ID Mandate**: Update `decider_node` in `services/orchestrator/graph/nodes/decider.py` to deterministically override `escalate`, `request_info`, and `close` actions to `auto_respond` (SAFE) unless an explicit ticket ID (e.g., `T-1001`, `TCK-1001`) is present in the prompt.
- **Frontend Fallback Cleanup**: Refactor `sendMessage` in `frontend-react/src/App.tsx` so empty-message polling fallback never appends duplicate plain-text messages if a valid approval card isn't present.

## Capabilities

### New Capabilities
- `sse-hitl-handshake-remediation`: Reliable SSE stream interrupt event emission, decider ticket ID constraints, and clean frontend fallback handling.

### Modified Capabilities
- None

## Impact

- `services/orchestrator/main.py`: `run_stream` SSE event generator logic.
- `services/orchestrator/graph/nodes/decider.py`: Ticket ID mandate guard in `decider_node`.
- `frontend-react/src/App.tsx`: `sendMessage` stream completion and fallback handling.
