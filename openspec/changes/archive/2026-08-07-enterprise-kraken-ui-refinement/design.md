## Context

The UI currently suffers from title duplication (**AKEA Cyber Ops** / **AKEA Cyber Operations Control Center**), persona pill duplication in top right header, awkward middle-of-the-screen scrollbar placement, and informal approval card styling.

## Goals / Non-Goals

**Goals:**

- Rename project title to **KRAKEN** and display it in ONE location (top left of sidebar).
- Remove main window header title duplicate and top right persona badge duplicate.
- Move vertical scrollbar to the far right edge of the viewport container.
- Redesign `InlineApprovalCard.tsx` into a high-contrast enterprise Datadog/Raycast alert card.

**Non-Goals:**

- Modifying backend FastAPI endpoints or database schemas.

## Decisions

- **Decision 1**: Standardize single brand name **KRAKEN** in `SessionSidebar.tsx` header bar.
- **Decision 2**: Apply `w-full overflow-y-auto` to the outer main flex container in `ruixen-moon-chat.tsx` so the scrollbar track attaches to the far right screen boundary, while message cards center via `max-w-3xl mx-auto`.
- **Decision 3**: Redesign `InlineApprovalCard.tsx` with a left border accent (`border-l-4 border-l-amber-500 bg-neutral-900/95`), metadata grid, clean prose reasoning, and solid enterprise action buttons.

## Risks / Trade-offs

- Purely visual UI adjustments with zero backend API risk.
