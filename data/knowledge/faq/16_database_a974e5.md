<!-- kraken-metadata: {"allowed_roles":["admin"],"category":"database","document_id":"DOC-016","effective_at":"2026-01-01T00:00:00Z","superseded_by":null,"untrusted_evidence":false} -->
# Database Change Procedure

Document ID: DOC-016
Dataset generation: northstar-v1
Effective: 2026-01-01
Access scope: admin

## Purpose
This synthetic Northstar policy defines controlled database operations for training and capability verification.

## Required controls
- Every production change has a rollback plan.
- Schema changes require review.
- Record migration evidence in the ticket.

## Evidence and escalation
Record the synthetic ticket, source document ID, decision, and trace ID. Escalate when required facts are missing; never invent approval or external execution.
