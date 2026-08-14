## Context

KRAKEN is a multi-agent AI security operations platform built with LangGraph, FastAPI microservices, and a React/TypeScript frontend. The backend is production-grade: it has RBAC security filtering, HITL approval gates, Redis-backed approval queues, PostgreSQL checkpoints, vector-based retrieval with Qdrant, and semantic caching. The UX layer has not kept pace. Sessions persist in `localStorage` but display no auto-titles or timestamps. The loading experience is a silent spinner. Errors surface as raw Axios exception strings. The HITL approval card shows a static summary, not editable fields. No mechanism exists for streaming agent step progress or exporting incident reports.

All changes are additive or surgical. No core agent logic is touched. Karpathy principle: touch only what you must.

## Goals / Non-Goals

**Goals:**
- Stream LangGraph node execution steps to the browser via Server-Sent Events
- Show typing/thinking animation while agent is processing
- Wrap React app in `ErrorBoundary`; surface all errors as structured chat cards, never raw traces
- Polish `SessionSidebar` with auto-generated session titles and relative timestamps (data already in `localStorage`)
- Add Gateway pre-flight middleware to classify and reject prompt injection attempts
- Add collapsible telemetry drawer per assistant message (RBAC role, chunk scores, trace ID, timing)
- Add `POST /v1/report/export` endpoint and frontend "Export PDF" button for session briefings
- Enrich HITL card for ticket creation with editable pre-filled fields extracted by the LLM

**Non-Goals:**
- Real authentication or SSO (persona switcher stays; it is an intentional design decision for demo/interview use)
- Rewriting or restructuring the LangGraph agent graph
- Modifying existing RBAC logic
- Adding new microservices (PDF export ships as an endpoint in the existing gateway or orchestrator)

## Decisions

### Decision 1: SSE via LangGraph `astream_events` — Node-Level, Not Token-Level

**Options considered:**
- Token-level streaming (word-by-word like ChatGPT)
- Node-level streaming (step-by-step per LangGraph node)

**Decision:** Node-level streaming.  
**Rationale:** Token streaming requires the LLM call to be un-buffered and threaded through multiple proxies (Gateway → Orchestrator → LLM). Node-level streaming uses LangGraph's built-in `astream_events(kind="on_chain_start"/"on_chain_end")` which is already available and requires zero changes to the agent graph. More importantly, node-step events visually demonstrate the multi-agent architecture — the audience sees *retriever → decider → executor → memory_writer* executing in sequence, which is the core value proposition of KRAKEN.

### Decision 2: Prompt Injection Guard as Gateway Middleware, Not Orchestrator Node

**Options considered:**
- Add a classifier node to the LangGraph graph
- Add pre-flight middleware in Gateway before forwarding

**Decision:** Gateway middleware.  
**Rationale:** Fails early, before consuming orchestrator resources. Keeps the agent graph clean. A regex + lightweight heuristic classifier is sufficient for a portfolio project; a production system would add an LLM-based classifier as a secondary pass (noted as a future enhancement, not implemented here per Karpathy's simplicity rule).

### Decision 3: PDF Export via `reportlab` in Orchestrator, Not New Microservice

**Decision:** Add `POST /v1/report/export` to the existing orchestrator (or gateway), using `reportlab` (pure Python, no system dependencies).  
**Rationale:** Adding a new microservice for PDF generation would require a new Docker layer, new service registration, new health checks, and new inter-service routing — disproportionate for a feature that generates a single document. `reportlab` is lightweight and renders formatted PDFs without requiring a headless browser (unlike WeasyPrint).

### Decision 4: Editable HITL Card Fields via Enriched Approval Payload

**Decision:** The Decider node, when routing `create_ticket`, serializes LLM-extracted fields (`affected_user`, `priority`, `category`, `description`) into the approval `payload` dict (already sent to the Approval Service). The `InlineApprovalCard` React component reads these fields and renders them as editable `<input>` elements. On "Approve", the edited values are submitted back.  
**Rationale:** The approval payload is already a freeform dict. No backend schema changes needed — only the Decider node's prompt and the InlineApprovalCard rendering logic change. Minimal surface area.

### Decision 5: Session Titles via First User Message, Client-Side Only

**Decision:** Auto-title = first 50 characters of first user message in that session, truncated with ellipsis. Generated client-side when a session receives its first message.  
**Rationale:** No backend API needed. Data already exists in `localStorage`. Pure `App.tsx` state update.

## Risks / Trade-offs

- **SSE and Render Free Tier**: Render's free tier may close idle SSE connections after 30 seconds. Mitigation: send a `ping` comment event every 15 seconds to keep the connection alive.
- **`reportlab` PDF formatting**: `reportlab` requires explicit layout code. The PDF will be functional but not pixel-perfect. Mitigation: define a fixed, simple template; no custom fonts.
- **Prompt Injection Heuristics vs. False Positives**: Regex-based detection may block legitimate security queries that contain instruction-like language. Mitigation: tune patterns conservatively; log blocked queries; allow override via `X-Operator-Role: operator` header (already present in the codebase).
- **Telemetry Drawer data availability**: Chunk scores and trace IDs must be enriched into `QueryResponse`. If the orchestrator does not return them, the drawer shows "N/A". Mitigation: add optional fields to `QueryResponse`; drawer renders gracefully with missing data.
