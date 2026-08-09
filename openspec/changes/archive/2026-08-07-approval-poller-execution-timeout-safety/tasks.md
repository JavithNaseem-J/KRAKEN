## 1. Approval Poller Execution Timeout & Error Safety

- [x] 1.1 Update `useApprovalPoller.ts` to enforce a 2-minute post-approval execution timeout and 5-consecutive-error limit
- [x] 1.2 Update `App.tsx` `onTimeout` handler to accept timeout reason and append system error message before clearing `pendingSessionId`
- [x] 1.3 Verify Vite build and test frontend error handling in browser
