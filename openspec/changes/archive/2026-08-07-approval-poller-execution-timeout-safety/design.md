## Context

`useApprovalPoller.ts` currently polls every 3 seconds while `pendingSessionId` is set, ignoring network/server errors for up to 15 minutes. If backend execution fails or disconnects after approval, `pendingSessionId` is never cleared and `Executing Authorized Action…` remains displayed in the header indefinitely.

## Goals / Non-Goals

**Goals:**

- Track `consecutiveErrors` in `useApprovalPoller.ts`. If 5 consecutive poll requests fail (15 seconds of errors), stop polling and trigger `onTimeout("Backend connection lost during action execution.")`.
- Add `MAX_EXECUTION_POLL_MS = 2 * 60_000` (2 minutes). If execution polling exceeds 2 minutes after approval, stop polling and trigger `onTimeout("Action execution timed out after 2 minutes.")`.
- Update `App.tsx` `onTimeout` handler to clear `pendingSessionId` and append an informative system error message.

**Non-Goals:**

- Changing HITL approval token expiration time (15 minutes).

## Decisions

- **Decision 1**: Poller tracks consecutive network errors and post-approval execution time to guarantee `pendingSessionId` is cleared within 2 minutes max (or 15s of network failure).

## Risks / Trade-offs

- None identified.
