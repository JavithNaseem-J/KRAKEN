## 1. Gateway Backend CORS Setup

- [x] 1.1 Add `CORSMiddleware` configuration to `services/gateway/main.py` allowing origins `http://localhost:5173` and `http://localhost:3000`

## 2. React + TypeScript Application Scaffold

- [x] 2.1 Initialize `frontend-react/` project using Vite, React 18, TypeScript, and Tailwind CSS
- [x] 2.2 Define TypeScript interfaces in `src/types/agent.ts` for `QueryResponse`, `PendingApproval`, `AgentMetadata`, and `ChatMessage`
- [x] 2.3 Create API client service in `src/services/api.ts` for Gateway `/v1/run` and Approval `/approve/{approval_id}/decision`

## 3. Sidebar & Multi-Role User Switcher

- [x] 3.1 Build `SessionSidebar` component with saved chat history, thread switching, new session creation, and local storage persistence
- [x] 3.2 Implement `UserRoleSwitcher` component allowing selection between `Alice` (Analyst), `Bob` (Security Lead), and `Admin` (Approver)

## 4. Inline Approval & Auto-Polling Workflow

- [x] 4.1 Build `InlineApprovalCard` component displaying requested action, risk level badge, reasoning summary, payload JSON preview, and `✓ Approve` / `✕ Reject` action buttons directly in the chat stream (no external tab redirection)
- [x] 4.2 Build `useApprovalPoller` custom hook to automatically poll `POST /v1/run` every 3 seconds while session status is `pending_approval`, instantly updating the chat when approved without manual refresh

## 5. Chat Interface & Cyber-Ops Design System

- [x] 5.1 Create `ChatMessage` and `ChatInput` components with Markdown rendering, syntax-highlighted code blocks, and copy buttons
- [x] 5.2 Build `ReasoningInspectorDrawer` slide-over side panel for inspecting step-by-step reasoning logic, verbatim evidence citations, documents read, and trace IDs
- [x] 5.3 Implement dark Cyber-Ops glassmorphism styling, glow badges, and responsive layout replacing rigid Streamlit design
