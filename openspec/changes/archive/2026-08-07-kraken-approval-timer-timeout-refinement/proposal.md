## Why

The current web application displays a `[K]` icon box in the sidebar header, cluttered approval card headers, informal top-right polling text (`Polling HITL Status...`), and lacks a live remaining time countdown for human approvals. Furthermore, when an approval times out after 15 minutes, the card remains active instead of auto-closing into a locked, expired state. Refining the sidebar branding to pure text **KRAKEN**, simplifying the approval card header, renaming the top-right polling text to `Awaiting Security Authorization…`, adding a live countdown timer (`Expires in MM:SS`), and locking expired approval requests ensures a professional enterprise-grade SOC experience.

## What Changes

- Display pure text **KRAKEN** in the top left sidebar header, removing the `[K]` icon box.
- Streamline the Approval Card header bar: remove shield icon, verbose `HUMAN AUTHORIZATION REQUIRED` text, `request_info` badge, and `CRITICAL RISK` badge, replacing them with a minimal `Action Approval Gate` title.
- Update top-right header polling text to `Awaiting Security Authorization…`.
- Add a 1-second interval live countdown timer (`Expires in MM:SS`) to pending approval cards.
- Implement automatic timeout handling: when an approval request times out, transition the card state to `expired`, disable action buttons, and render a locked status banner (`🔒 AUTHORIZATION EXPIRED`).

## Capabilities

### New Capabilities

- `kraken-text-branding`: Renders pure text **KRAKEN** in the sidebar header without icon boxes.
- `approval-card-minimal-header`: Simplifies approval gate card header bars into a clean, un-cluttered layout.
- `approval-countdown-timer`: Displays live countdown timers (`Expires in MM:SS`) for pending human authorization requests.
- `approval-timeout-autoclose`: Locks expired approval cards into a disabled `AUTHORIZATION EXPIRED` state.

### Modified Capabilities

None.

## Impact

- `frontend-react/src/components/SessionSidebar.tsx`: Pure text **KRAKEN** title.
- `frontend-react/src/components/ui/ruixen-moon-chat.tsx`: Top-right polling text update (`Awaiting Security Authorization…`).
- `frontend-react/src/components/InlineApprovalCard.tsx`: Minimal header, live countdown timer, and locked expired state.
- `frontend-react/src/App.tsx`: Synchronize expired approval state on poller timeout.
