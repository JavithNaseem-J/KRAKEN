## Why

Displaying raw 36-character UUID strings (`session: 2c58ed31-6246...` and `Approval ID: 7ff3c0c2-9da0...`) and static boilerplate labels (`Security Protocol v1.0`) in the primary workspace adds unnecessary visual noise and distracts from core agent workflows. Cleaning up top bar headers to show active session titles and streamlining approval cards with truncated reference chips brings the interface up to enterprise SOC software standards.

## What Changes

- Replace the raw `session: <uuid>` text in the top header bar with the active Session Title (e.g., *"Helpdesk Ticket Request"*) or a fallback title when no title exists.
- Truncate Approval IDs inside `InlineApprovalCard.tsx` to a clean `#<short-hash>` badge with a 1-click copy button.
- Remove static boilerplate text `Security Protocol v1.0` from the `InlineApprovalCard` footer.

## Capabilities

### New Capabilities

- `clean-header-session-title`: Replaces raw session UUID strings in the top header bar with human-readable session titles.
- `streamlined-approval-card-metadata`: Truncates approval ID GUIDs to clean reference badges with copy action and removes static protocol boilerplate labels.

### Modified Capabilities

None.

## Impact

- `frontend-react/src/components/ui/ruixen-moon-chat.tsx`: Top header bar title rendering.
- `frontend-react/src/components/InlineApprovalCard.tsx`: Approval ID truncation, copy action, and footer cleanup.
