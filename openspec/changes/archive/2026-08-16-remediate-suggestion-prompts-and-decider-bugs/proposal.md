## Why

When users run suggestion queries in the Cyber Ops console, three out of four prompts either trigger unintended Human-in-the-Loop (HITL) approval cards or display a 5-second thinking indicator before disappearing without leaving an assistant response. This occurs due to uninitialized variable bugs in `decider.py` (`UnboundLocalError`), overly broad decider action classification for ticket status queries, and lost response payloads when LangGraph pauses execution during streaming.

## What Changes

- **Fix `UnboundLocalError` in Decider**: Explicitly initialize `verified_actions: list[dict[str, Any]] = []` and `highest_risk: str = "SAFE"` in `services/orchestrator/graph/nodes/decider.py`.
- **Enforce Read-Only Guard for Status Inquiries**: Implement a code-level guard in `decider.py` so queries inquiring about ticket statuses (`"status of ticket..."`) deterministically map to `auto_respond` without triggering HITL escalation.
- **Harden Stream Interrupt & Fallback Rendering**: Update `App.tsx` and `api.ts` so SSE interrupt payloads (`pending_approval`) and fallback polling reliably render approval cards or system error messages without dropping messages from chat state.

## Capabilities

### New Capabilities
- `suggestion-query-triage-remediation`: Remediation of decider node execution, read-only status query safety guards, and frontend stream completion handling for UI suggestion prompts.

### Modified Capabilities
- None.

## Impact

- `services/orchestrator/graph/nodes/decider.py`
- `frontend-react/src/App.tsx`
- `frontend-react/src/services/api.ts`
