## Context

While `pendingSessionId === activeSessionId` is active during background poller execution, the top-right header currently renders a static amber `Awaiting Security Authorization…` badge regardless of whether the user has approved the action.

## Goals / Non-Goals

**Goals:**

- Inspect `messages` in `ruixen-moon-chat.tsx` to determine `latestApprovalMsg = messages.slice().reverse().find(m => m.approval_id)`.
- Render `Awaiting Security Authorization…` (Amber badge + `Clock`) when `latestApprovalMsg?.approval_state === 'pending'`.
- Render `Executing Authorized Action…` (Emerald badge + `Loader2` spin) when `latestApprovalMsg?.approval_state === 'approved'`.

**Non-Goals:**

- Modifying polling intervals or backend API routes.

## Decisions

- **Decision 1**: Top-right header badge evaluates `latestApprovalMsg?.approval_state` to switch dynamically between `Awaiting Security Authorization…` and `Executing Authorized Action…`.

## Risks / Trade-offs

- None identified.
