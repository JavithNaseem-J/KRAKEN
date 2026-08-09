## Context

When an action is approved, `approval_state` becomes `'approved'`. However, background execution takes 2-5 seconds. Previously, `APPROVED & EXECUTED` was shown immediately upon approval click.

## Goals / Non-Goals

**Goals:**

- Introduce `isExecuting?: boolean` prop on `InlineApprovalCard` and `ChatMessage`.
- While `isExecuting` is true, render `APPROVED & EXECUTING…` (emerald text + `Loader2` spin).
- When `isExecuting` becomes false (after execution completes), render `APPROVED & EXECUTED` (emerald text + `Check`).

**Non-Goals:**

- Modifying backend approval API payloads.

## Decisions

- **Decision 1**: `isExecuting` is derived in `ruixen-moon-chat.tsx` as `pendingSessionId === activeSessionId && message.approval_state === 'approved'`.

## Risks / Trade-offs

- None identified.
