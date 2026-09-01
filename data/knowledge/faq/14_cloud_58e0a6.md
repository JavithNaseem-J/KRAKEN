<!-- kraken-metadata: {"allowed_roles":["tier1_analyst","security_lead","incident_commander","admin"],"category":"cloud","document_id":"DOC-014","effective_at":"2026-07-01T00:00:00Z","superseded_by":null,"untrusted_evidence":false} -->
# Cloud IAM Standard

Document ID: DOC-014
Dataset generation: northstar-v1
Effective: 2026-07-01
Access scope: tier1_analyst

## Purpose
This synthetic Northstar policy defines controlled cloud operations for training and capability verification.

## Required controls
- Use roles instead of long-lived keys.
- MFA is required for privileged access.
- Review inactive grants monthly.

## Evidence and escalation
Record the synthetic ticket, source document ID, decision, and trace ID. Escalate when required facts are missing; never invent approval or external execution.
