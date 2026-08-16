## 1. Responder Prompting Fix

- [x] 1.1 Update `services/orchestrator/graph/nodes/responder.py` to inject an explicit approval override instruction when `approval_status == 'approved'`.

## 2. Orchestrator Session State Reset

- [x] 2.1 Update `/run` and `/run/stream` in `services/orchestrator/main.py` to clear residual `snapshot.next` on new user turns.

## 3. Frontend Polling Synchronization

- [x] 3.1 Update `handleApprovalResolved` in `frontend-react/src/App.tsx` to set `pendingSessionId` to null on approval resolution.

## 4. End-to-End Verification

- [x] 4.1 Execute 2-step verification script confirming approved ticket creation followed by VPN query execution on the same thread.
