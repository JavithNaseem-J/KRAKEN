<!-- kraken-metadata: {"allowed_roles":["security_lead","incident_commander","admin"],"category":"platform","document_id":"DOC-015","effective_at":"2026-08-01T00:00:00Z","superseded_by":null,"untrusted_evidence":false} -->
# Kubernetes Incident Runbook

Document ID: DOC-015
Dataset generation: northstar-v1
Effective: 2026-08-01
Access scope: security_lead

## Purpose
This synthetic Northstar policy defines controlled platform operations for training and capability verification.

## Required controls
- Check node pressure and workload health.
- Drain only after impact review.
- Preserve cluster events.

## Evidence and escalation
Record the synthetic ticket, source document ID, decision, and trace ID. Escalate when required facts are missing; never invent approval or external execution.
