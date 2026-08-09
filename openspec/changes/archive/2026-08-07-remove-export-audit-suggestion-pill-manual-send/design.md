## Context

The UI needs header bar simplification (removing Export Audit Log) and UX refinement for quick action suggestion pills so they fill the input box without auto-submitting.

## Goals / Non-Goals

**Goals:**

- Remove `Export Audit Log` button and `exportSessionLogs` handler from `ruixen-moon-chat.tsx`.
- Create a `handlePillClick(text: string)` helper in `ruixen-moon-chat.tsx` that calls `setMessage(text)` and focuses `textareaRef`.
- Connect all quick action pills (`SLA Guidelines`, `VPN Connection`, `Ticket T-1001 Status`, `Create IT Ticket`) to `handlePillClick`.

**Non-Goals:**

- Modifying underlying backend APIs or message structure.

## Decisions

- **Decision 1**: `handlePillClick` updates input value state, triggers `adjustHeight()`, and focuses `textareaRef.current`. Execution remains gated until `handleSend()` is triggered by clicking **Send** or pressing Enter.

## Risks / Trade-offs

- None identified; pure frontend interaction improvement.
