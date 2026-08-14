## Why

KRAKEN's backend is production-grade. The frontend and UX experience is not. Users see raw error stack traces when things go wrong, blank screens during 3-8 second agent execution waits, no real-time feedback of the multi-agent graph executing, and no mechanism to review AI reasoning or export incident briefings. The conversational ticket creation flow also stops short — the HITL approval card shows a static summary rather than a pre-filled editable form the analyst can verify before approving. These gaps make KRAKEN feel like a demo rather than an enterprise platform. All eight gaps are addressable without touching core agent logic.

## What Changes

- **SSE Streaming**: Add `GET /v1/run/stream` endpoint emitting Server-Sent Events per LangGraph node step. Frontend renders live agent step badges as the graph executes.
- **Typing Animation**: Replace the silent loading spinner with an animated "thinking" indicator while awaiting backend response.
- **Error Boundaries**: Wrap the React app in an `ErrorBoundary` component. All caught errors render a friendly incident card (never a raw stack trace). Backend 4xx/5xx responses surface as structured error messages in the chat.
- **Session Sidebar Polish**: Sessions already persist in `localStorage`. Add auto-generated titles (first user message, truncated), relative timestamps ("2 hours ago"), and visual active-session indicator.
- **Prompt Injection Guard**: Add a pre-flight middleware in the Gateway that detects and blocks common prompt injection patterns before the request reaches the LangGraph orchestrator.
- **Security Telemetry Drawer**: Add a collapsible side drawer that opens when the user clicks any assistant message, showing: RBAC clearance role, retrieved chunk relevance scores, trace ID, and execution timing.
- **PDF Incident Briefing Export**: Add `POST /v1/report/export` endpoint that generates a formatted executive incident briefing PDF from a completed session. Frontend adds an "Export PDF" button per session.
- **Editable HITL Card for Ticket Creation**: When the Decider routes to `create_ticket`, the LLM extracts structured fields (user, priority, category, description) and serializes them into the approval payload. The HITL card renders editable fields the analyst can correct before approving.

## Capabilities

### New Capabilities

- `sse-streaming`: Real-time Server-Sent Events endpoint streaming LangGraph node execution steps to the frontend as they happen.
- `prompt-injection-guard`: Gateway middleware that classifies and blocks prompt injection attempts before they reach the orchestrator.
- `telemetry-drawer`: Frontend component that displays per-message AI reasoning metadata: RBAC role, chunk scores, trace ID, execution timing.
- `pdf-export`: Backend endpoint and frontend button to generate executive incident briefing PDFs from completed sessions.
- `editable-hitl-card`: Enhanced HITL approval card that renders pre-filled, editable ticket fields extracted by the LLM from natural language before human approval.

### Modified Capabilities

- `session-management`: Existing sessions persist in localStorage; requirements change to add auto-generated session titles from first user message and relative timestamps in sidebar.
- `error-handling`: Existing error handling surfaces raw messages; requirement changes to always render structured error cards in chat UI and never expose stack traces.

## Impact

- **Backend**: `services/orchestrator/main.py` — new SSE streaming route; `services/gateway/main.py` — prompt injection middleware; new `services/report/` microservice or endpoint for PDF generation.
- **Frontend**: `src/App.tsx` — ErrorBoundary wrapper, SSE event handling; `src/components/ui/ruixen-moon-chat.tsx` — typing animation, telemetry drawer toggle; `src/components/InlineApprovalCard.tsx` — editable form fields; `src/components/SessionSidebar.tsx` — auto-titles and timestamps.
- **Shared models**: `shared/models/agent.py` — enrich `QueryResponse` with `trace_id`, `chunk_scores`, `execution_ms` fields.
- **Dependencies**: `reportlab` or `weasyprint` for PDF generation; no other new backend dependencies.
