## 1. 404 Graceful Expiration & Status Sync

- [x] 1.1 Update `InlineApprovalCard.tsx` to handle HTTP 404 fetch errors by setting `isExpired = true` and invoking `onExpired` callback
- [x] 1.2 Update `ChatMessage.tsx` to sync timestamp line status badge with `isExpired` / `approval_state === 'expired'`
- [x] 1.3 Update `App.tsx` session loader and `handleApprovalExpired` callback to synchronize session state
- [x] 1.4 Verify Vite build and test frontend rendering in browser
