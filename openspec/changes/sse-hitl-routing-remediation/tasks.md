## 1. Orchestrator SSE Interrupt Event Emission

- [x] 1.1 Update `run_stream` event generator in `services/orchestrator/main.py` to yield a `pending_approval` SSE data event when `snapshot.next` is true after stream completion.

## 2. Decider Ticket ID Requirement

- [x] 2.1 Enforce ticket ID regex match requirement in `services/orchestrator/graph/nodes/decider.py` to override `escalate`, `request_info`, and `close` to `auto_respond` if no ticket ID is present in the prompt.

## 3. Frontend Stream Completion Clean-up

- [x] 3.1 Refactor `sendMessage` in `frontend-react/src/App.tsx` so streaming completion payloads with `status: "pending_approval"` append a single clean approval card.
