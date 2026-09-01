<!-- kraken-metadata: {"allowed_roles":["public","end_user","tier1_analyst","security_lead","incident_commander","admin"],"category":"engineering","document_id":"DOC-022","effective_at":"2026-07-01T00:00:00Z","superseded_by":null,"untrusted_evidence":false} -->
# Secure Coding Standard

Document ID: DOC-022
Dataset generation: northstar-v1
Effective: 2026-07-01
Access scope: public

## Purpose
This synthetic Northstar policy defines controlled engineering operations for training and capability verification.

## Required controls
- Validate untrusted input.
- Use parameterized database operations.
- Do not expose model reasoning or secrets.

## Evidence and escalation
Record the synthetic ticket, source document ID, decision, and trace ID. Escalate when required facts are missing; never invent approval or external execution.
