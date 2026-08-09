## Context

The UI currently renders raw 36-character session and approval UUIDs and static "Security Protocol v1.0" labels in primary user views. Cleaning these up improves visual hierarchy and alignment with enterprise SOC console standards.

## Goals / Non-Goals

**Goals:**

- Pass `sessionTitle?: string` to `RuixenMoonChat.tsx` and render `sessionTitle || "New Session"` instead of `session: <uuid>`.
- In `InlineApprovalCard.tsx`, truncate `approvalId` to `Ref: #${approvalId.slice(0, 8)}` with a copy-to-clipboard button.
- Remove `Security Protocol v1.0` text from `InlineApprovalCard.tsx` footer.

**Non-Goals:**

- Modifying underlying session UUID generation logic in the backend.

## Decisions

- **Decision 1**: Top header bar displays `sessionTitle || "New Session"` alongside the status pulsing dot.
- **Decision 2**: Approval card footer renders `Ref: #${approvalId.slice(0, 8)}` with a copy icon, omitting static protocol strings.

## Risks / Trade-offs

- None identified.
