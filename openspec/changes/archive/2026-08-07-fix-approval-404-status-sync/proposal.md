## Why

When an approval request times out or is deleted from Redis (e.g. after 15 minutes), opening or viewing that approval card causes `fetchApprovalDetails` to return an HTTP 404 error. Currently, the UI displays a raw, unhandled error banner (`Request failed with status code 404`) inside the card, while the timestamp line below the card contradicts the card status by continuing to show `AUTHORIZATION PENDING`. Treating HTTP 404 errors as expired security requests and synchronizing approval states cleanly across the entire card and message stream eliminates visual contradictions and provides a seamless enterprise-grade experience.

## What Changes

- Handle HTTP 404 errors during approval detail fetching gracefully: set `isExpired = true`, suppress raw 404 error boxes, and lock the card into `🔒 AUTHORIZATION EXPIRED` state.
- Add an `onExpired` callback to `InlineApprovalCard` that notifies `App.tsx` and `ChatMessage.tsx` to update the message's `approval_state` to `'expired'` in session state.
- Synchronize `ChatMessage.tsx` timestamp status rendering so that expired cards render `🔒 AUTHORIZATION EXPIRED` below the card rather than `AUTHORIZATION PENDING`.
- On application / session initialization in `App.tsx`, automatically mark any pending approval messages older than 15 minutes as `approval_state = 'expired'`.

## Capabilities

### New Capabilities

- `approval-404-graceful-expiration`: Gracefully transitions 404 approval detail fetch errors into locked expired states without raw HTTP error alerts.
- `approval-unified-status-sync`: Synchronizes expired approval states across card components, timestamp status badges, and persisted session states.

### Modified Capabilities

None.

## Impact

- `frontend-react/src/components/InlineApprovalCard.tsx`: 404 error handling & `onExpired` callback invocation.
- `frontend-react/src/components/ChatMessage.tsx`: Unified status badge rendering.
- `frontend-react/src/App.tsx`: Auto-expiration of stale pending messages on load & state sync handler.
