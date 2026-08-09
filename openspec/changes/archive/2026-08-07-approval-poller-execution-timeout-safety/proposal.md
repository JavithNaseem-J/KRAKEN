## Why

When an action is approved by the user, the frontend polls `POST /v1/run` waiting for the backend agent to complete execution. Currently, if the backend encounters a network disconnect or unhandled exception, `useApprovalPoller` catches errors silently and polls for up to 15 minutes, causing the UI to hang indefinitely showing `Executing Authorized Action…`. Adding a 2-minute post-approval execution timeout and consecutive error limit prevents UI hangs and provides clear feedback when polling disconnects.

## What Changes

- Add a 5-consecutive-error limit (15 seconds of failed network/server requests) to `useApprovalPoller.ts`.
- Add a 2-minute post-approval execution timeout to `useApprovalPoller.ts`.
- When either error threshold is triggered, clear `pendingSessionId` and append an error message to the session stream: *"Backend action execution disconnected or timed out."*

## Capabilities

### New Capabilities

- `approval-poller-error-resilience`: Prevents indefinite UI hangs during post-approval action execution by setting consecutive error limits and 2-minute timeouts.

### Modified Capabilities

None.

## Impact

- `frontend-react/src/hooks/useApprovalPoller.ts`: Error counting and 2-minute execution timeout.
- `frontend-react/src/App.tsx`: Handling execution timeout callbacks and clearing `pendingSessionId`.
