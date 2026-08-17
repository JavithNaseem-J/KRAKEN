## Context

Users running suggestion queries in the Cyber Ops console experienced `UnboundLocalError` inside `decider.py`, false HITL escalation on ticket status inquiries, and disappearing message indicators when HITL interrupts occurred during SSE streaming.

## Technical Design

### 1. `decider.py` Scope & Guard Hardening
- Initialize `verified_actions: list[dict[str, Any]] = []` and `highest_risk: str = "SAFE"` at the start of decision processing.
- Add code-level status inquiry detector (`is_status_query`):
  - Matches `"status of ticket"`, `"ticket status"`, `"check status of"`.
  - Forces `action_name = "auto_respond"` and `verified_actions = [{"action_name": "auto_respond", "action_payload": {...}, "risk_level": "SAFE"}]`.

### 2. Frontend SSE & Response State Cleanup (`App.tsx` & `api.ts`)
- Ensure `streamAgentQuery` captures `PendingApproval` payloads when SSE streaming completes or pauses.
- Guard fallback handling in `App.tsx` so that any non-empty `PendingApproval` or `QueryResponse` appends a visible message or approval card to chat state, preventing empty thinking state collapses.

## Verification Plan

### Automated & Integration Tests
- Run automated test script against all 4 suggestion queries (`test_4prompts.ps1`):
  1. `"What is the SLA for critical security vulnerabilities?"` -> `auto_respond`
  2. `"What is the status of ticket T-1001?"` -> `auto_respond`
  3. `"Create an IT ticket for a broken monitor replacement for user Alice."` -> `create_ticket` (CRITICAL, HITL Card)
  4. `"How do I connect to the corporate VPN?"` -> `auto_respond`
