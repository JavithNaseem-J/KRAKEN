## Context

Enterprise SOC teams require auditable evidence chains, session export capabilities, and explicit developer environment indicators.

## Goals / Non-Goals

**Goals:**

- Add an Audit Service deep link in `ReasoningInspectorDrawer.tsx` pointing to `http://localhost:8006/audit/events/{trace_id}`.
- Add an Export Transcript button in `ruixen-moon-chat.tsx` header for downloading session logs in JSON format.
- Label the persona area in `SessionSidebar.tsx` with a `Developer Testing Persona` badge.

**Non-Goals:**

- Replacing local dev persona switcher logic with full OAuth2 servers.

## Decisions

- **Decision 1**: Build a client-side JSON export helper in `ruixen-moon-chat.tsx` that formats messages, timestamps, and reasoning traces into a downloadable file (`kraken-session-{sessionId}.json`).
- **Decision 2**: Render an `ExternalLink` button in `ReasoningInspectorDrawer.tsx` next to OpenTelemetry trace IDs linking directly to `http://localhost:8006/audit/events/{traceId}`.

## Risks / Trade-offs

- None identified; purely additive frontend SOC enhancements.
