<!-- kraken-metadata: {"allowed_roles":["public","end_user","tier1_analyst","security_lead","incident_commander","admin"],"category":"security","document_id":"DOC-023","effective_at":"2026-08-01T00:00:00Z","superseded_by":null,"untrusted_evidence":false} -->
# Secrets Handling Standard

Document ID: DOC-023
Dataset generation: northstar-v1
Effective: 2026-08-01
Access scope: public

## Purpose
This synthetic Northstar policy defines controlled security operations for training and capability verification.

## Required controls
- Store secrets in managed secret storage.
- Never commit or log credentials.
- Rotate exposed values immediately.

## Evidence and escalation
Record the synthetic ticket, source document ID, decision, and trace ID. Escalate when required facts are missing; never invent approval or external execution.
