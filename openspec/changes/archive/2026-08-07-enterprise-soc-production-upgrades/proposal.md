## Why

To complete the remaining enterprise production recommendations discussed during exploration, KRAKEN needs production-grade features for auditability, compliance reporting, and user context. Adding an Audit Service deep link in the Reasoning Inspector, session transcript export (JSON/TXT format), and clear developer testing persona badges equips Security Operations Center (SOC) teams with production-ready compliance tools.

## What Changes

- Add a direct **Audit Log Trace** button in `ReasoningInspectorDrawer.tsx` linking to `http://localhost:8006/audit/events/{trace_id}`.
- Add an **Export Transcript** button in `ruixen-moon-chat.tsx` header to download session audit logs as a formatted JSON/TXT file.
- Update `SessionSidebar.tsx` bottom persona area with a `Developer Testing Persona` badge to explicitly distinguish developer persona switching from SAML SSO / Okta production auth.

## Capabilities

### New Capabilities

- `audit-trace-deep-link`: Provides direct navigation to Audit Service event logs for any assistant message trace.
- `session-transcript-export`: Allows SOC analysts to export chat session audit transcripts for incident compliance.
- `dev-persona-sso-badge`: Clarifies developer testing personas versus enterprise SSO auth in the sidebar.

### Modified Capabilities

None.

## Impact

- `frontend-react/src/components/ReasoningInspectorDrawer.tsx`: Audit Service deep link button.
- `frontend-react/src/components/ui/ruixen-moon-chat.tsx`: Header export transcript button.
- `frontend-react/src/components/SessionSidebar.tsx`: Developer testing persona badge.
