## Context

When human approval was granted for an action, `responder_node` saw pre-approval refusal text in `reasoning` and triggered its refusal rule, outputting a refusal despite successful execution. In addition, `snapshot.next` in LangGraph was not cleared on subsequent turns, causing subsequent queries on the session to fail with an approval prompt error.

## Technical Design

### 1. `responder.py` Prompt Override for Approved Actions
- In `responder_node` ([`services/orchestrator/graph/nodes/responder.py`](file:///f:/DSML/KRAKEN/services/orchestrator/graph/nodes/responder.py)), check if `approval_status == 'approved'` or if `action_result` indicates `success: true`.
- When true, append a mandatory system prompt instruction:
  - `"HUMAN APPROVAL WAS GRANTED AND ACTION EXECUTED: The requested action has been approved by an authorized operator and executed successfully (result: {action_result}). You MUST NOT deny or refuse the request. Generate a professional confirmation response detailing the successful execution and ticket ID."`

### 2. Orchestrator State Reset on New Turn
- In `services/orchestrator/main.py`, before processing any non-empty user query in `/run` or `/run/stream`:
  - If `snapshot.next` is present and `snapshot.values` shows `approval_status in ('approved', 'rejected')` or `final_answer` is present, execute `graph.aupdate_state(config, None, as_node="executor")` to clear the pending node execution pointer.

### 3. Frontend Polling Synchronization
- In `frontend-react/src/App.tsx`, update `handleApprovalResolved` so `setPendingSessionId(null)` is called immediately when an approval or rejection decision is submitted.

## Verification Plan

### Automated & Manual Tests
- Execute test script running the exact 2-step sequence:
  1. Submit `"Create an IT ticket for a broken monitor replacement for user Alice."` -> returns `pending_approval`.
  2. Approve the request via approval API -> returns confirmation text containing ticket ID `TCK-XXXX`.
  3. Submit `"How do I connect to the corporate VPN?"` on the same session -> returns `auto_respond` with VPN connection details.
