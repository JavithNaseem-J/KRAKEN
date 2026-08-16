## ADDED Requirements

### Requirement: Decider Node Execution Safety & Ticket Status Safeguard
The `decider_node` SHALL initialize `verified_actions` and `highest_risk` before processing LLM decisions. Inquiries regarding ticket status (`"status of ticket..."`, `"ticket status"`) SHALL map to `auto_respond` (`SAFE`, no HITL) unless explicit write intent is present.

#### Scenario: Status Inquiries Map to Auto Respond
- **WHEN** a user asks "What is the status of ticket T-1001?"
- **THEN** the system SHALL select `auto_respond` with `risk_level: SAFE` and avoid triggering a Human-in-the-Loop interrupt.

#### Scenario: IT Ticket Creation Triggers HITL Card
- **WHEN** a user requests "Create an IT ticket for a broken monitor replacement for user Alice."
- **THEN** the system SHALL select `create_ticket` with `risk_level: CRITICAL` and present a single pending approval card in the UI stream.

#### Scenario: General Policy & FAQ Inquiries Auto Respond
- **WHEN** a user asks "What is the SLA for critical security vulnerabilities?" or "How do I connect to the corporate VPN?"
- **THEN** the system SHALL return the factual answer via `auto_respond` without error or interface interruption.
