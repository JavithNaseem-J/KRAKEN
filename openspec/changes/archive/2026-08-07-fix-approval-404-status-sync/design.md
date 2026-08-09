## Context

When an approval request in Redis is cleaned up or expired, fetching details returns a 404 error. The UI currently displays a raw 404 error banner while the timestamp line below the card contradicts it by showing `AUTHORIZATION PENDING`.

## Goals / Non-Goals

**Goals:**

- Catch 404 errors in `InlineApprovalCard.tsx` when calling `fetchApprovalDetails`: set `isExpired = true`, suppress raw 404 error banner, and invoke `onExpired(approvalId)`.
- Update `App.tsx` and `ChatMessage.tsx` to handle `onExpired`: transition `message.approval_state` to `'expired'` in session state.
- Ensure `ChatMessage.tsx` timestamp line renders `🔒 AUTHORIZATION EXPIRED` when `approval_state === 'expired'` or `isExpired` is true.

**Non-Goals:**

- Changing backend Redis TTL duration.

## Decisions

- **Decision 1**: In `InlineApprovalCard.tsx`, if `fetchApprovalDetails` throws an error containing `404` or `not found`, set `isExpired(true)` and call `onExpired?.(approvalId)`.
- **Decision 2**: Pass `onExpired` callback through `ChatMessage.tsx` to `InlineApprovalCard.tsx`, which triggers `updateSession` in `App.tsx`.

## Risks / Trade-offs

- None; pure UX state synchronization fix.
