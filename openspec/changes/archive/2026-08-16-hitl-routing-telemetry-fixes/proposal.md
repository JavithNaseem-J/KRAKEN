## Why

The agent triage system experiences four critical runtime anomalies:
1. Read-only ticket status queries (e.g., "What is the status of ticket T-1001?") trigger false-positive HITL approval gates.
2. New user prompts submitted after a paused HITL gate cause the orchestrator to resume and display stale output from the previous query (e.g., answering about T-1001 when asked about VPN).
3. SSE stream dropouts trigger empty polling requests that produce duplicate "pending approval" cards with missing Authorize/Deny buttons due to orchestrator/approval-service memory state desynchronization.
4. Clicking anywhere inside a chat message bubble unexpectedly opens the Telemetry inspector drawer.

Fixing these issues ensures accurate action routing, clean session thread isolation, reliable HITL card rendering, and intuitive UI interactions.

## What Changes

- **Decider Scoping & Enforcement**: Enforce strictly that informational status queries and FAQs route to `auto_respond` (READ), reserving `escalate`/`create_ticket` solely for explicit state-mutating requests.
- **Orchestrator Thread Isolation**: Update stream and REST execution handlers to cleanly reset thread state when a new prompt arrives on an interrupted session, preventing stale responder execution.
- **Approval Card & State Sync**: Sync orchestrator HITL pauses with the Approval Service store and gracefully handle 404s in `InlineApprovalCard` to retain Authorize/Deny action buttons.
- **UI Interaction Precision**: Restrict the Telemetry Drawer trigger strictly to explicit footer button clicks in `ChatMessage.tsx`.

## Capabilities

### New Capabilities
- `hitl-triage-resilience`: Reliable ticket status routing, HITL gate persistence, and thread state isolation.

### Modified Capabilities
- None

## Impact

- `services/orchestrator/graph/nodes/decider.py`: Routing rule enforcement for read inquiries.
- `services/orchestrator/main.py`: Clean thread state handling and approval registration.
- `frontend-react/src/components/ChatMessage.tsx`: Removal of full-bubble click handler.
- `frontend-react/src/components/InlineApprovalCard.tsx`: Resilient approval details fetching and button rendering.
