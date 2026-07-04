# Xiarch Security Consultancy — Policy and FAQ

## 1. Scope of Services
Xiarch is a premier cybersecurity consultancy specializing in:
- **Penetration Testing**: Web Applications, Mobile Apps (iOS/Android), Cloud Infrastructure (AWS/Azure/GCP), Network Pentesting, and Source Code Reviews.
- **Compliance Audits**: ISO 27001 certification prep, SOC 2 Type I/II readiness, PCI-DSS compliance, and HIPAA reviews.
- **Vulnerability Assessments**: Automated scanning, manual verification, and configuration auditing.

## 2. Rules of Engagement for Pentesting
- Testing can only commence once a signed Authorization Letter and Rules of Engagement (RoE) document are in place.
- Production testing must occur within agreed maintenance windows, typically between 10:00 PM and 04:00 AM local time, to minimize business interruption.
- Exploitation of Critical vulnerabilities (e.g., Remote Code Execution, SQL Injection, Authentication Bypass) must be halted immediately once confirmed. The findings must be reported to the client's designated security contact within 1 hour.

## 3. SLA and Response Times
Xiarch categorizes client inquiries and reported security findings into four priority levels:
- **Critical Severity**: Active data breaches, Remote Code Execution (RCE) findings, or active system compromise. 
  - **SLA Commitment**: Response within 1 hour, mitigation plan within 4 hours.
  - **Escalation**: Immediate escalation to Tier 3 (Principal Security Architect) and notification to Technical Director.
- **High Severity**: SQLi, IDOR, Privilege Escalation, and authentication flaws in scope.
  - **SLA Commitment**: Response within 4 hours, mitigation advice within 8 hours.
  - **Escalation**: Escalate to Tier 2 (Senior Security Consultant) if unresolved in 4 hours.
- **Medium Severity**: Information disclosure, CSRF, and out-of-date service versions.
  - **SLA Commitment**: Response within 8 hours, resolution advice within 24 hours.
- **Low Severity**: SSL/TLS configuration issues, missing security headers, and best-practice recommendations.
  - **SLA Commitment**: Response within 24 hours, resolution within 72 hours.

## 4. Support and Escalation Tiers
- **Tier 1 (Associate Security Consultant)**: Handles initial ticket triaging, basic vulnerability questions, and simple compliance checklist lookup.
- **Tier 2 (Senior Security Consultant)**: Handles complex validation, manual exploit verification, and draft report reviews.
- **Tier 3 (Principal Security Architect / Technical Director)**: Handles critical findings, custom exploit chain reviews, and high-stakes client escalation.
- **Tier 4 (CTO)**: Oversees critical SLA breaches, legal/compliance blockages, and emergency incident response coordination.

## 5. Report Deliverables
- **Draft Pentest Report**: Delivered within 5 business days of testing completion.
- **Final Pentest Report**: Delivered within 2 business days of receiving client feedback on the draft.
- **Re-testing Policy**: One complimentary re-testing cycle is provided within 30 days of the draft report delivery.

## 6. Compliance Auditing Guidelines
- **ISO 27001 Audit**: Requires evidence review of all Annex A controls. No audits will proceed without a signed Scope Statement.
- **SOC 2 Type II**: Requires a minimum 3-month (preferably 6-month) observation window of operational logs and policy adherence evidence.
- **HIPAA Compliance**: Requires a signed Business Associate Agreement (BAA) prior to reviewing any systems containing Protected Health Information (PHI).
- **PCI-DSS Audits**: Conducted by a Qualified Security Assessor (QSA). Full Self-Assessment Questionnaire (SAQ) support is available.
