## Why

Currently, when a user authorizes an action by clicking "Authorize Execution", the top-right header status badge continues to display `Awaiting Security Authorization…` while the agent is actively executing the action in the background. Updating the header badge dynamically to reflect the current authorization lifecycle (`Awaiting Security Authorization…` ➔ `Executing Authorized Action…` ➔ Hidden/Complete) provides real-time clarity and eliminates status confusion.

## What Changes

- Update `ruixen-moon-chat.tsx` header status badge logic to evaluate the active message's `approval_state`.
- When `approval_state === 'pending'`, display `Awaiting Security Authorization…` (Amber badge with `Clock` icon).
- When `approval_state === 'approved'` and background execution is active, display `Executing Authorized Action…` (Emerald badge with spinning `Loader2` icon).
- When execution finishes (`pendingSessionId` becomes `null`), hide the badge cleanly.

## Capabilities

### New Capabilities

- `dynamic-header-approval-status-badge`: Dynamically transitions the top-right header status badge through pending, executing, and completed states.

### Modified Capabilities

None.

## Impact

- `frontend-react/src/components/ui/ruixen-moon-chat.tsx`: Header badge status evaluation and rendering.
