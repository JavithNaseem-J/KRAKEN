## 1. Phase 1 — Quick Frontend Wins (Thinking Animation, Error Boundaries, Session Polish)

- [x] 1.1 Add `TypingIndicator` component to `ruixen-moon-chat.tsx` — animated three-dot pulse displayed while `disabled === true` and no streaming events are present
- [x] 1.2 Create `ErrorBoundary.tsx` React class component that catches unhandled errors and renders a styled incident card with a generated incident ID
- [x] 1.3 Wrap the root `<App />` in `index.tsx` with `<ErrorBoundary>`
- [x] 1.4 Update `App.tsx` `handleError` to catch Axios errors and push a structured error message into the session's messages array instead of logging to console
- [x] 1.5 Update `App.tsx` `newSession()` and message append logic to auto-set `session.title` from the first 50 chars of the first user message
- [x] 1.6 Update `SessionSidebar.tsx` to display relative timestamps using a `formatRelative()` utility (e.g., "just now", "3 hours ago", "Aug 13")
- [x] 1.7 Write unit test: `test_error_boundary_renders_card.tsx` — simulate a component throw and assert incident card renders
- [x] 1.8 Write unit test: `test_session_auto_title.ts` — assert first message sets title correctly

## 2. Phase 2 — Prompt Injection Guard (Backend Gateway Middleware)

- [x] 2.1 Add `_INJECTION_PATTERNS` compiled regex list to `services/gateway/main.py` covering: "ignore all previous instructions", "disregard your", "you are now", "pretend you are", "act as if", "new persona", "override system"
- [x] 2.2 Add `_check_prompt_injection(text: str, operator: bool) -> bool` helper function in `services/gateway/main.py`
- [x] 2.3 Wire `_check_prompt_injection` into the `/v1/run` route body pre-flight check — return HTTP 400 with structured error if triggered (skip check if `X-Operator-Role: operator`)
- [x] 2.4 Write unit test: `test_prompt_injection_guard` — assert 5 known injection strings are blocked, 3 legitimate security queries pass through
- [x] 2.5 Verify `npm run build` passes and existing 180 tests remain green after change

## 3. Phase 3 — SSE Streaming (Backend + Frontend)

- [x] 3.1 Add `GET /v1/run/stream` route to `services/orchestrator/main.py` using FastAPI `StreamingResponse` and LangGraph `graph.astream_events()`
- [x] 3.2 Emit one SSE `data:` line per `on_chain_start` / `on_chain_end` event with `{node, status, elapsed_ms}` JSON payload
- [x] 3.3 Add `: ping` comment every 15 seconds to prevent Render free tier connection timeouts
- [x] 3.4 Add `streamAgentQuery(text, sessionId, apiKey, onEvent)` function to `frontend-react/src/services/api.ts` using `EventSource` or `fetch` with `ReadableStream`
- [x] 3.5 Update `App.tsx` `handleSend` to use `streamAgentQuery` and call `onEvent` to update a `streamingSteps` state array
- [x] 3.6 Add `AgentStepBadges` component to `ruixen-moon-chat.tsx` that renders `streamingSteps` as live step badges below the typing indicator
- [x] 3.7 Wire `GET /v1/run/stream` proxy through Gateway `services/gateway/main.py`
- [x] 3.8 Verify SSE connection stays alive for 60+ seconds with ping events

## 4. Phase 4 — Telemetry Drawer

- [x] 4.1 Add optional fields `trace_id: str | None`, `chunk_scores: list[float] | None`, `execution_ms: int | None` to `QueryResponse` in `shared/models/agent.py`
- [x] 4.2 Populate `trace_id` (from `session_id`), `execution_ms`, and `chunk_scores` (from retriever result) in `_build_response()` in `services/orchestrator/main.py`
- [x] 4.3 Update `ChatMessageType` TypeScript type in `frontend-react/src/types/agent.ts` with optional `telemetry` field
- [x] 4.4 Create `TelemetryDrawer.tsx` component — slide-in panel showing RBAC role, chunk scores (top-3 with bar chart), trace ID, execution time
- [x] 4.5 Wire click handler on assistant `ChatMessage` bubble to toggle `TelemetryDrawer` open/closed
- [x] 4.6 Verify missing telemetry fields render "N/A" without crashing

## 5. Phase 5 — PDF Incident Briefing Export

- [x] 5.1 Add `reportlab` to `requirements.txt` and `pyproject.toml`
- [x] 5.2 Create `services/gateway/report.py` with `generate_incident_pdf(session_data: dict) -> bytes` function using `reportlab` canvas
- [x] 5.3 Add `POST /v1/report/export` route in `services/gateway/main.py` — accepts `{session_id, messages, persona}` JSON, returns `application/pdf` response
- [x] 5.4 Add `exportSessionPDF(sessionId, messages, persona, apiKey)` function to `frontend-react/src/services/api.ts`
- [x] 5.5 Add "Export PDF" button to `SessionSidebar.tsx` per session item — triggers download on click
- [x] 5.6 Write unit test: `test_pdf_generation` — assert `generate_incident_pdf` returns non-empty bytes for a mock session
- [x] 5.7 Verify PDF downloads correctly in browser and contains session messages

## 6. Phase 6 — Editable HITL Card for Ticket Creation

- [x] 6.1 Update Decider node prompt in `services/orchestrator/graph/nodes/decider.py` to extract structured ticket fields (`affected_user`, `priority`, `category`, `description`) and include them in the approval action payload
- [x] 6.2 Update `InlineApprovalCard.tsx` to detect `action_name === "create_ticket"` and render editable `<input>` fields for each extracted ticket field
- [x] 6.3 Update approval submission logic in `useApprovalPoller.ts` or `App.tsx` to include edited field values in the approval decision payload sent to the Approval Service
- [x] 6.4 Update ticket handler in `services/action/handlers/ticket_handler.py` to read override values from the approval resolution payload when present
- [x] 6.5 Write unit test: `test_editable_hitl_ticket_fields` — assert decider extracts fields from "Create ticket for Alice's broken monitor" into approval payload
- [x] 6.6 Manual verification: submit "Create an IT ticket for Alice's broken monitor", change priority in HITL card, approve, confirm ticket created with edited values

## 7. Final Verification

- [x] 7.1 Run full test suite: assert ≥180 tests pass
- [x] 7.2 Run `npm run build` — assert no TypeScript errors and build succeeds
- [x] 7.3 Git commit all changes with message: `feat: production polish — SSE streaming, error boundaries, telemetry drawer, PDF export, editable HITL card, prompt injection guard`
- [x] 7.4 Push to GitHub `main` and trigger Render deploy
