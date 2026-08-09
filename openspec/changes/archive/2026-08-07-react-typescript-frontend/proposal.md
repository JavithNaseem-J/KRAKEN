## Why

The current Streamlit interface requires users to navigate to an external web page to approve HITL security actions and manually refresh the chat to view updated results. Replacing Streamlit with a modern Vite + React + TypeScript single-page application will consolidate approval workflows inline, enable real-time status polling, and provide a Cyber-Ops design system with a multi-role user switcher for security testing.

## What Changes

- **Replace Streamlit Frontend**: Deprecate `frontend/app.py` in favor of a Vite + React + TypeScript web application (`frontend-react/`).
- **Inline HITL Approval Cards**: Embed interactive approval cards directly in the chat stream with instant `✓ Approve` and `✕ Reject` actions, eliminating external tab redirection.
- **Automated Background Polling**: Poll Gateway status automatically when an action is pending approval, updating the chat UI as soon as execution resumes.
- **Multi-Role User Switcher**: Allow switching user identities (`Alice` [Tier 1 Analyst], `Bob` [Security Lead], `Admin` [Approver]) on the fly in the sidebar to simulate role-based authorization.
- **Cyber-Ops Glassmorphism Theme**: Implement a dark theme system with glow status badges, Inter typography, syntax-highlighted code blocks, and JSON payload inspection drawers.
- **Gateway CORS Support**: Add `CORSMiddleware` to `services/gateway/main.py` allowing cross-origin requests from the React dev server (`http://localhost:5173`).

## Capabilities

### New Capabilities
- `react-frontend-chat`: Interactive React + TypeScript chat interface with persistent session sidebar, markdown rendering, and background status polling.
- `inline-approval-workflow`: Embedded approval cards in chat stream for reviewing and resolving HITL actions without opening external tabs.
- `multi-role-user-switcher`: On-the-fly user role selector allowing switching between Alice, Bob, and Admin to test security policies.
- `cyber-ops-design-system`: Dark glassmorphism design system with responsive layout, syntax highlighting, and Reasoning Inspector drawer.

### Modified Capabilities
- `gateway-api`: Add CORS middleware configuration to support browser preflight `OPTIONS` requests from web frontends.

## Impact

- **Frontend**: Streamlit (`frontend/app.py`) is replaced by `frontend-react/` (Vite + React 18 + TypeScript + Tailwind CSS).
- **Backend Gateway**: `services/gateway/main.py` adds FastAPI `CORSMiddleware`.
- **Dependencies**: React, Vite, TypeScript, Tailwind CSS, Lucide Icons, Axios/httpx-compatible client.
