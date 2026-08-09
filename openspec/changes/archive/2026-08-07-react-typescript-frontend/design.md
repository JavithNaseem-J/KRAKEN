## Context

The current Streamlit app (`frontend/app.py`) is a monolithic Python UI that requires users to navigate to an external web page (`http://localhost:8004/approve/...`) to approve HITL security actions and manually refresh the chat page to retrieve updated results. The user requested replacing Streamlit with a modern Vite + React + TypeScript web application incorporating an inline HITL approval workflow, automatic status polling, a multi-role user switcher (`Alice`, `Bob`, `Admin`), and a Cyber-Ops glassmorphism theme system.

## Goals / Non-Goals

**Goals:**
- Replace Streamlit with a Vite + React + TypeScript single-page application in `frontend-react/`.
- Provide inline approval cards directly in the chat stream with instant `✓ Approve` and `✕ Reject` controls.
- Implement automatic background status polling when an action is in `pending_approval` state.
- Add a multi-role user switcher in the sidebar (`Alice` [Analyst], `Bob` [Security Lead], `Admin` [Approver]).
- Deliver a Cyber-Ops dark glassmorphism design system with responsive layout, syntax highlighting, and a Reasoning Inspector drawer.
- Add `CORSMiddleware` to `services/gateway/main.py` allowing preflight cross-origin requests from the React app (`http://localhost:5173`).

**Non-Goals:**
- Replacing FastAPI backend microservices or changing Orchestrator LangGraph state machine logic.
- Building a full OAuth2/OIDC provider (user role switching is simulated via request parameters and headers for testing policy rules).

## Decisions

### Decision 1: Single Page Application Stack (Vite + React 18 + TypeScript + Tailwind CSS)
- **Choice**: Vite + React 18 with TypeScript and Tailwind CSS.
- **Rationale**: Vite provides sub-second HMR and lightweight bundle sizes without heavy server-side framework overhead. Tailwind CSS allows rapid creation of custom dark glassmorphism tokens.
- **Alternatives Considered**: Next.js (unnecessary server-side routing overhead for an internal agent console), Streamlit (inflexible UI layout and tab switching).

### Decision 2: Multi-Role User Switcher (`Alice`, `Bob`, `Admin`)
- **Choice**: Session state role dropdown in the sidebar that injects `user_id` (`alice`, `bob`, `admin`) into Gateway `/v1/run` requests.
- **Rationale**: Allows instant testing of how risk gating and HITL approval routing adapt to different user roles without requiring complex auth logins.

### Decision 3: Background Status Polling Lifecycle
- **Choice**: When a response returns `status: "pending_approval"`, the chat component mounts a 3-second interval poller sending `POST /v1/run` with `{"message": "", "session_id": session_id}` until status becomes `completed`.
- **Rationale**: Reuses the Gateway checkpointer state inspection logic introduced in Orchestrator `/run`, ensuring zero user friction after approving actions in the UI.

### Decision 4: Backend Gateway CORS Configuration
- **Choice**: Add `CORSMiddleware` to `services/gateway/main.py` allowing `http://localhost:5173` and `http://localhost:3000`.
- **Rationale**: Eliminates browser cross-origin preflight errors when the Vite dev server sends `POST` and `OPTIONS` requests to `http://localhost:8000`.

## Risks / Trade-offs

- **[Risk]** Polling frequency could create unnecessary Gateway traffic if left unhandled.
  - **Mitigation**: Limit polling to active `pending_approval` sessions with a max duration timeout of 15 minutes (matching HITL token TTL).
- **[Risk]** CORS configuration opening local origins.
  - **Mitigation**: Restrict `allow_origins` strictly to configured frontend dev/prod URLs.

## Migration Plan

1. Initialize `frontend-react/` using Vite + React + TypeScript + Tailwind CSS.
2. Implement types, API client, multi-role switcher, chat components, inline approval card, and reasoning drawer.
3. Configure `CORSMiddleware` in `services/gateway/main.py`.
4. Update launch commands to serve React app on `:5173`.
