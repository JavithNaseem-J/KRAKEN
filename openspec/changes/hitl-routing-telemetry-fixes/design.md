## Context

The KRAKEN AI cybersecurity agent stack utilizes FastAPI microservices, LangGraph for graph state orchestration, Groq/Llama-3.3-70b for LLM inference, and React for the frontend user console. Four specific interaction bugs affect triage routing, state isolation across user prompts, approval registration, and telemetry UI event triggers.

## Goals / Non-Goals

**Goals:**
- Enforce strict READ vs. WRITE prompt constraints in `decider_node` so informational ticket queries resolve to `auto_respond`.
- Ensure new user queries on an interrupted thread reset execution state without leaking previous query answers.
- Synchronize HITL approval registration with the Approval Service (port 8004) and ensure UI cards render Authorize/Deny buttons reliably.
- Restrict Telemetry Inspector drawer activation to explicit button clicks in `ChatMessage.tsx`.

**Non-Goals:**
- Modifying underlying vector search embedding algorithms.
- Changing authentication JWT/API-key validation logic.

## Decisions

1. **Decider Prompt Hard Constraint**: Update `decider.py` rules to mandate that any query asking for information, status, or FAQ regarding an existing ticket MUST select `auto_respond`. `escalate` is reserved exclusively for explicit security incident escalations with critical vulnerability evidence.
2. **Clean Thread State Reset**: When a new user query arrives in `/run` or `/run/stream` while `snapshot.next` is true, clear the thread checkpoint state before running `astream_events` or `ainvoke`, avoiding execution of the old responder node.
3. **Approval Service Sync & UI Card Graceful Fallback**: Register all HITL interrupts directly with the Approval Service (`http://127.0.0.1:8004/pending`) and update `InlineApprovalCard.tsx` to handle 404 responses with retry logic rather than instant expiration.
4. **Scoped Event Handler**: Remove `onClick` from the container `div` in `ChatMessage.tsx` and attach `onInspectTelemetry` solely to the `<button>` badge element.

## Risks / Trade-offs

- **[Risk]**: Clearing interrupted thread state on new message disallows approving a pending HITL card after a user types a new message.
  - **Mitigation**: Once a user types a new prompt, the old unapproved action is treated as superseded/cancelled by the new query.
