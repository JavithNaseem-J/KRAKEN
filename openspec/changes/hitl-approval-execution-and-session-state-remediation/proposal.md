## Why

When human approval is granted for a CRITICAL action (such as `create_ticket`), `responder_node` misinterprets prior pre-approval refusal reasoning and generates a text refusal response despite successful action execution. Furthermore, subsequent queries on the same session thread receive "A CRITICAL triage action requires human approval" due to uncleared interrupt state in LangGraph checkpoints.

## What Changes

- **Override Refusal Mandate on Approved Execution**: Update `services/orchestrator/graph/nodes/responder.py` to inject an explicit approval override instruction into the LLM system prompt when `approval_status == 'approved'` and `action_result` reports success.
- **Ensure Clean Interrupt State Reset**: Update `services/orchestrator/main.py` so new incoming query requests explicitly clear any residual `snapshot.next` interrupt state before running a new graph turn.
- **Frontend Approval Poller Synchronization**: Update `frontend-react/src/App.tsx` to clear `pendingSessionId` upon approval resolution so background polling stops cleanly.

## Capabilities

### New Capabilities
- `hitl-approval-fulfillment-and-state-reset`: End-to-end fulfillment confirmation after human approval and reliable state reset across multi-turn chat sessions.

### Modified Capabilities
- None.

## Impact

- `services/orchestrator/graph/nodes/responder.py`
- `services/orchestrator/main.py`
- `frontend-react/src/App.tsx`
