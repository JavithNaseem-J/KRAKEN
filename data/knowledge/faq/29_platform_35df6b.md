<!-- kraken-metadata: {"allowed_roles":["tier1_analyst","security_lead","incident_commander","admin"],"category":"platform","document_id":"DOC-029","effective_at":"2026-06-01T00:00:00Z","superseded_by":null,"untrusted_evidence":false} -->
# Certificate Rotation Standard

Document ID: DOC-029
Dataset generation: northstar-v1
Effective: 2026-06-01
Access scope: tier1_analyst

## Purpose
This synthetic Northstar policy defines controlled platform operations for training and capability verification.

## Required controls
- Current certificates rotate 30 days before expiry.
- The old 90-day exception is superseded.
- Validate the complete trust chain.

## Evidence and escalation
Record the synthetic ticket, source document ID, decision, and trace ID. Escalate when required facts are missing; never invent approval or external execution.
