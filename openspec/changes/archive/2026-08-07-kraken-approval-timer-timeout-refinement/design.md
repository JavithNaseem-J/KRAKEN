## Context

The UI currently has icon clutter in the sidebar header (`[K] KRAKEN`), header clutter in `InlineApprovalCard.tsx`, informal polling text (`Polling HITL Status...`), and lacks live remaining time countdown or auto-closing locked state for expired approvals.

## Goals / Non-Goals

**Goals:**

- Display pure text **KRAKEN** in the top left sidebar header.
- Streamline `InlineApprovalCard.tsx` header: title `Action Approval Gate`, subtitle `Security clearance required before proceeding`.
- Update top-right header polling text to `Awaiting Security Authorization…`.
- Implement live countdown timer (`Expires in MM:SS`) in `InlineApprovalCard.tsx`.
- Lock expired approval cards with status `🔒 AUTHORIZATION EXPIRED`.

**Non-Goals:**

- Modifying backend FastAPI endpoints or Redis queue TTL logic.

## Decisions

- **Decision 1**: Calculate remaining time in `InlineApprovalCard.tsx` using `setInterval(1000)` based on `details.expires_at` (or 15 min fallback from message timestamp).
- **Decision 2**: When remaining seconds reach `<= 0` or `state === 'expired'`, automatically disable buttons and render `🔒 AUTHORIZATION EXPIRED`.
- **Decision 3**: On poller timeout in `App.tsx`, update the message `approval_state` to `'expired'` to lock the card.

## Risks / Trade-offs

- Purely frontend UI/UX enhancements with zero backend API risk.
