## Context

When an agent graph execution triggers a HITL interrupt, `astream_events` completes without yielding a `response` object, causing `streamAgentQuery` in `App.tsx` to return `finalResponse = undefined`. The frontend's fallback `runAgentQuery('')` executes an empty poll against the interrupted thread, appending duplicate plain-text messages. Additionally, general questions containing words like "critical" trigger `escalate` due to lack of strict ticket ID enforcement.

## Goals / Non-Goals

**Goals:**
- Update `run_stream` generator to yield a `pending_approval` SSE event when `snapshot.next` is true.
- Add strict ticket ID validation in `decider_node` so prompts lacking ticket IDs default to `auto_respond`.
- Refactor `sendMessage` in `App.tsx` to handle SSE completion payloads cleanly.

**Non-Goals:**
- Altering vector similarity thresholds or Qdrant collection schemas.

## Decisions

1. **SSE Interrupt Event Emission**: In `services/orchestrator/main.py`, check `snapshot.next` after `astream_events`. If interrupted, extract `approval_id`, store record in `_IN_MEMORY_APPROVAL_MAP`, and yield `data: {"node": "interrupt", "status": "pending_approval", "response": {...}}\n\n`.
2. **Ticket ID Regex Guard**: In `decider.py`, if `action_name` is `escalate`, `request_info`, or `close` and `user_message` lacks a ticket ID regex match, force `action_name = "auto_respond"` and `highest_risk = "SAFE"`.
3. **Frontend Message Deduplication**: In `App.tsx`, rely on `finalRes` from `streamAgentQuery`. If `isPendingApproval(finalRes)`, append the approval card directly.

## Risks / Trade-offs

- **[Risk]**: If the frontend SSE connection breaks mid-stream, fallback polling is still required.
  - **Mitigation**: `/v1/run` returns full QueryResponse or pending_approval payload with valid `approval_id`.
