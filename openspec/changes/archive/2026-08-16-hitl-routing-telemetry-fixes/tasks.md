## 1. Routing Rules & Scoping

- [x] 1.1 Enforce read-only status query rule in `services/orchestrator/graph/nodes/decider.py` so inquiries like "What is the status of ticket T-1001?" map to `auto_respond`.

## 2. Orchestrator Thread Isolation

- [x] 2.1 Refactor `/run` and `/run/stream` endpoints in `services/orchestrator/main.py` to cleanly reset interrupted thread state on new user prompts without resuming previous responder nodes.
- [x] 2.2 Ignore empty/whitespace-only polling messages (`""` or `.`) from initiating new graph executions or appending duplicate pending approval cards.

## 3. Approval Card Sync & Recovery

- [x] 3.1 Verify `_register_approval` in `services/orchestrator/graph/nodes/executor.py` registers pending approval IDs with Approval Service (port 8004).
- [x] 3.2 Update `frontend-react/src/components/InlineApprovalCard.tsx` to retry fetching details on transient 404s before setting `isExpired=true`.

## 4. Telemetry Drawer UI Event Scoping

- [x] 4.1 Remove container `onClick` handler from message bubble in `frontend-react/src/components/ChatMessage.tsx`.
- [x] 4.2 Restrict `onInspectTelemetry` trigger exclusively to the explicit `[Telemetry]` button badge.
