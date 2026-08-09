## Why

The current web interface duplicates project titles across the sidebar and header, repeats the active user persona badge in the top right, positions the vertical scrollbar awkwardly next to the chat text column, and renders an informal approval card. Streamlining the project title to **KRAKEN** in one single location, cleaning up top right status items, positioning the scrollbar at the far right edge of the viewport, and polishing the Approval Gate into a sleek Datadog/Raycast enterprise alert elevates the application to production-grade enterprise standards.

## What Changes

- Rename project title to **KRAKEN** and display it in ONE location (top left of sidebar).
- Remove redundant project title from main window header bar.
- Remove duplicate active persona badge (`Admin · Approver`) from the top right corner.
- Move vertical scrollbar track to the far right edge of the viewport by making the full-width chat viewport container scrollable with centered message content.
- Redesign the Inline Approval Gate into a sleek, Datadog-style enterprise security card with clean metadata grid, left accent border, and high-contrast control buttons.

## Capabilities

### New Capabilities

- `kraken-brand-layout`: Standardizes single enterprise brand placement (**KRAKEN**) and removes duplicate header titles and persona badges.
- `viewport-scrollbar-alignment`: Aligns chat viewport vertical scrollbar track to the far right screen edge.
- `enterprise-approval-gate`: Formats Human-in-the-Loop authorization gates into high-contrast enterprise security alert cards.

### Modified Capabilities

None.

## Impact

- `frontend-react/src/components/SessionSidebar.tsx`: Single **KRAKEN** brand title.
- `frontend-react/src/components/ui/ruixen-moon-chat.tsx`: Top header cleanup and far right viewport scrollbar alignment.
- `frontend-react/src/components/InlineApprovalCard.tsx`: Datadog/Raycast style enterprise approval card.
