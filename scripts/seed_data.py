"""Seed script — populates dev/test data with Xiarch security tickets."""

from __future__ import annotations

import json
from pathlib import Path

TICKETS_DIR = Path(__file__).parent.parent / "data" / "knowledge" / "tickets"
WORKSPACE_DIR = Path(__file__).parent.parent / "data" / "workspace"

SAMPLE_TICKETS = [
    {
        "id": "TK-001",
        "title": "Critical RCE in photo upload endpoint",
        "status": "open",
        "priority": "critical",
        "category": "pentest",
        "description": "Found a critical Remote Code Execution (RCE) vulnerability in the user profile photo upload endpoint. We were able to upload a webshell and execute system commands.",
    },
    {
        "id": "TK-002",
        "title": "SOC 2 Type II audit readiness scheduling",
        "status": "open",
        "priority": "medium",
        "category": "compliance",
        "description": "Client wants to schedule their SOC 2 Type II readiness audit for their AWS cloud infrastructure next month. Need to check auditor availability.",
    },
    {
        "id": "TK-003",
        "title": "HIPAA BAA sign-off request",
        "status": "open",
        "priority": "high",
        "category": "compliance",
        "description": "Client asks if HIPAA requires a Business Associate Agreement (BAA) sign-off prior to Xiarch testing their EHR portal.",
    },
    {
        "id": "TK-004",
        "title": "TLS 1.0 and weak ciphers flagged in scan",
        "status": "open",
        "priority": "low",
        "category": "vulnerability",
        "description": "A vulnerability scan flagged SSL/TLS weak ciphers and TLS 1.0 enabled on the client's public payment portal.",
    },
    {
        "id": "TK-005",
        "title": "External pentesting requested without RoE",
        "status": "open",
        "priority": "critical",
        "category": "pentest",
        "description": "A client is asking to start an external penetration test immediately on their production servers, but they have not signed the Rules of Engagement (RoE) yet.",
    },
    {
        "id": "TK-006",
        "title": "Privilege escalation identified in staging portal",
        "status": "open",
        "priority": "high",
        "category": "pentest",
        "description": "Found privilege escalation from Associate to Admin role in the client staging portal via IDOR parameter manipulation.",
    },
    {
        "id": "TK-007",
        "title": "ISO 27001 Annex A control evidence checklist submission",
        "status": "resolved",
        "priority": "medium",
        "category": "compliance",
        "description": "Client submitted their Annex A control evidence checklist for review. Associate checked and confirmed it meets the requirements.",
    },
    {
        "id": "TK-008",
        "title": "SQL Injection in search bar of portal",
        "status": "resolved",
        "priority": "critical",
        "category": "pentest",
        "description": "SQL Injection vulnerability was identified in the main search bar. Client confirmed mitigation and Associate verified the fix.",
    },
    {
        "id": "TK-009",
        "title": "SSL certificate expiration warning on staging",
        "status": "open",
        "priority": "medium",
        "category": "vulnerability",
        "description": "Automated scan reports that the SSL certificate for staging.clientdomain.com will expire in 5 days.",
    },
    {
        "id": "TK-010",
        "title": "HIPAA scoping query regarding PHI storage",
        "status": "open",
        "priority": "high",
        "category": "compliance",
        "description": "Client wants to know if storing encrypted Patient Health Information (PHI) in an AWS S3 bucket meets the HIPAA physical safeguards.",
    },
    {
        "id": "TK-011",
        "title": "AWS configuration audit for compliance",
        "status": "open",
        "priority": "medium",
        "category": "audit",
        "description": "Requesting a full review of AWS IAM roles, security groups, and cloudtrail logs to prepare for their upcoming SOC 2 audit.",
    },
    {
        "id": "TK-012",
        "title": "Cross-Site Scripting in admin dashboard feedback page",
        "status": "open",
        "priority": "high",
        "category": "pentest",
        "description": "Stored XSS vulnerability in the admin feedback page. Any feedback submitted can execute arbitrary JavaScript in the admin session.",
    },
    {
        "id": "TK-013",
        "title": "Draft report feedback and re-test timeframe",
        "status": "open",
        "priority": "medium",
        "category": "pentest",
        "description": "Client provided comments on the draft pentest report and wants to know when we can start the complimentary re-testing cycle.",
    },
    {
        "id": "TK-014",
        "title": "SOC 2 Type II evidence window question",
        "status": "open",
        "priority": "low",
        "category": "compliance",
        "description": "Client is asking if a 2-month observation window is sufficient for their upcoming SOC 2 Type II audit.",
    },
    {
        "id": "TK-015",
        "title": "Auth bypass via password reset token reusability",
        "status": "open",
        "priority": "critical",
        "category": "pentest",
        "description": "Password reset tokens do not expire after use. This allows an attacker to reuse a captured token to change any user password.",
    },
    {
        "id": "TK-016",
        "title": "Missing security headers on web login page",
        "status": "open",
        "priority": "low",
        "category": "vulnerability",
        "description": "Scan indicates that HSTS and Content-Security-Policy (CSP) headers are missing on the main web login page.",
    },
    {
        "id": "TK-017",
        "title": "PCI-DSS SAQ-D review assistance",
        "status": "open",
        "priority": "medium",
        "category": "compliance",
        "description": "Client needs help completing Section 2 of Self-Assessment Questionnaire D (SAQ-D) regarding cardholder data flow diagrams.",
    },
]


def main() -> None:
    TICKETS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    # Write to knowledge base
    out_kb = TICKETS_DIR / "sample_tickets.json"
    out_kb.write_text(json.dumps(SAMPLE_TICKETS, indent=2), encoding="utf-8")
    print(f"Seeded {len(SAMPLE_TICKETS)} tickets -> {out_kb}")

    # Write to workspace
    out_ws = WORKSPACE_DIR / "tickets.json"
    out_ws.write_text(json.dumps(SAMPLE_TICKETS, indent=2), encoding="utf-8")
    print(f"Seeded {len(SAMPLE_TICKETS)} tickets -> {out_ws}")

    print("Seed complete.")


if __name__ == "__main__":
    main()
