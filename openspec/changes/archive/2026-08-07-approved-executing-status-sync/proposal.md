## Why

When a user approves an action, the UI currently transitions immediately to `APPROVED & EXECUTED` even while the backend is actively performing the operation. Updating the card and timestamp status to display `APPROVED & EXECUTING…` during active execution, and reserving `APPROVED & EXECUTED` strictly for when execution finishes, ensures status accuracy and alignment with user expectations.

## What Changes

- Add `isExecuting?: boolean` prop to `InlineApprovalCard.tsx` and `ChatMessage.tsx`.
- Pass `isExecuting` from `ruixen-moon-chat.tsx` based on `pendingSessionId === activeSessionId && message.approval_state === 'approved'`.
- When `isApproved` and `isExecuting` are true, display `APPROVED & EXECUTING…` with a spinning `Loader2` icon inside the card and on the timestamp line.
- When `isApproved` is true and `isExecuting` is false, display `APPROVED & EXECUTED` with a `Check` icon.

## Capabilities

### New Capabilities

- `approved-executing-status-feedback`: Displays `APPROVED & EXECUTING…` while background execution is in progress, transitioning to `APPROVED & EXECUTED` only upon completion.

### Modified Capabilities

None.

## Impact

- `frontend-react/src/components/InlineApprovalCard.tsx`: Card status banner rendering logic.
- `frontend-react/src/components/ChatMessage.tsx`: Timestamp line status rendering logic.
- `frontend-react/src/components/ui/ruixen-moon-chat.tsx`: Passing `isExecuting` prop to `ChatMessage`.
