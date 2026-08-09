## Why

The current frontend includes an Export Audit Log button in the header bar which is unnecessary for general user workflows, and clicking quick action suggestion pills (e.g. `Create IT Ticket`) immediately triggers query execution without giving users an opportunity to review or edit the prompt beforehand. Removing the export audit button simplifies the header bar, and changing suggestion pill behavior to fill the input field rather than auto-submitting prevents unintended query executions.

## What Changes

- Remove the `Export Audit Log` button and its associated `exportSessionLogs` download handler completely from `ruixen-moon-chat.tsx`.
- Update quick action suggestion pills (`SLA Guidelines`, `VPN Connection`, `Ticket T-1001 Status`, `Create IT Ticket`) so that clicking a pill populates the input textarea (`setMessage(...)`), sets focus to the input box, and waits for the user to explicitly tap **Send** before executing.

## Capabilities

### New Capabilities

- `remove-export-audit-header`: Completely removes the Export Audit Log button from the header bar.
- `suggestion-pills-manual-send`: Ensures quick action suggestion pills populate the input text without auto-executing queries until Send is explicitly tapped.

### Modified Capabilities

None.

## Impact

- `frontend-react/src/components/ui/ruixen-moon-chat.tsx`: Header bar cleanup and suggestion pills click handler update.
