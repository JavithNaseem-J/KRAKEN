# Xiarch Cybersecurity & Enterprise IT Support Knowledge Base

## 1. Incident Response & Threat Triage Standard Operating Procedures (SOPs)

### SOP-01: Phishing & Credential Harvesting Mitigation
- **Detection**: Reported via Outlook PhishAlert button or user inquiry to secops@xiarch.com.
- **Triage Steps**:
  1. Analyze email headers for SPF, DKIM, and DMARC alignment.
  2. Extract suspicious URLs or attachment hashes and run sandboxed analysis via VirusTotal/Cuckoo.
  3. If malignant, initiate domain/URL block on Palo Alto Firewalls and Cloudflare WAF.
  4. Query Active Directory / Azure AD for users who clicked or authenticated on the rogue portal.
  5. Mandate an immediate password reset and invalidate active OAuth tokens for affected accounts via `Revoke-AzureADUserAllRefreshToken`.
- **SLA**: Initial response < 15 mins for P1 (C-Suite or widespread phish), < 1 hour for P2.

### SOP-02: Malware & Ransomware Endpoint Containment
- **Trigger**: CrowdStrike Falcon alert with High or Critical severity.
- **Action**:
  1. Isolate endpoint using CrowdStrike Network Containment API.
  2. Capture RAM dump and memory snapshot via volatility script.
  3. Verify BitLocker status and active volume shadow copies.
  4. Perform AD account disablement if process execution originated from compromised domain credentials.
  5. Re-image endpoint using WDS/MDT template after forensics extraction.

### SOP-03: Suspicious Login & Anomaly Detection
- **Trigger**: Conditional Access flag for impossible travel, unfamiliar location, or anonymous IP address.
- **Resolution Path**:
  - Contact user via verified secondary channel (Duo push / phone call).
  - If unconfirmed, revoke session tokens immediately and trigger MFA re-enrollment.

---

## 2. Identity & Access Management (IAM) Policies

### IAM-01: Password & MFA Policies
- **Length & Complexity**: Minimum 16 characters, passphrase format recommended. No routine expiration required if Duo/Azure AD MFA is enforced.
- **Multi-Factor Authentication (MFA)**: Mandatory for all external, VPN, and SaaS access. SMS MFA is deprecated; FIDO2 WebAuthn keys or Duo Push with Number Matching are required.
- **Account Lockout**: 5 failed attempts result in a 30-minute lockout. Unlocking requires identity verification via SecOps portal.

### IAM-02: Privileged Access Management (PAM)
- **Zero Standing Privileges (ZSP)**: Administrative rights (Domain Admin, AWS AdministratorAccess, K8s cluster-admin) must be requested JIT (Just-In-Time) via CyberArk / Teleport.
- **Approval Requirement**: All JIT elevation requests require approval from a SecOps Lead or System Owner.
- **Session Duration**: JIT access defaults to 2 hours, maximum 8 hours per change window.

### IAM-03: SSH & API Key Governance
- Long-lived SSH keys in `/home/user/.ssh/authorized_keys` are forbidden.
- Teleport Certificate Authority (CA) must issue short-lived SSH X.509/RSA certificates.
- API keys must be stored in AWS Secrets Manager or HashiCorp Vault. Hardcoding secrets in source code triggers automated GitHub secret scanning push blocks.

---

## 3. Network, VPN & Remote Access Protocols

### NET-01: GlobalProtect VPN Access
- **Client**: Palo Alto GlobalProtect v6.2+.
- **Authentication**: Azure AD SAML + Duo MFA.
- **Split Tunneling**: Disabled for security traffic; all web traffic routes through corporate Prisma Access SASE.
- **Troubleshooting Connection Failures**:
  - `Error 51`: Service not started. Run `net start PanGPS` in elevated CMD.
  - `Portal Host Unreachable`: Verify DNS resolution for `vpn.xiarch.com`. Ensure local firewall port 443/4500 UDP is unblocked.
  - `Certificate Error`: Update client root CA store using Company Portal.

### NET-02: Firewall Rule & Port Modification Requests
- Direct modification of Palo Alto or AWS Security Groups requires an official Change Advisory Board (CAB) ticket.
- **Forbidden Rules**: Opening `0.0.0.0/0` to SSH (22), RDP (3389), SMB (445), or Database ports (5432, 3306, 1433, 27017) is strictly prohibited and triggers immediate automated remediation.

---

## 4. Endpoint Management & Data Loss Prevention (DLP)

### EDP-01: Device Enrollment & Encryption
- All Windows devices must be domain-joined to Azure AD / Intune with BitLocker 256-bit XTS enabled.
- macOS devices must be enrolled in Jamf Pro with FileVault enabled and Escrow Key stored in Intune.

### EDP-02: USB & Storage Media Policy
- USB mass storage access is blocked by default via Intune Endpoint Protection policy.
- Temporary USB write access requires a High-risk request approved by the CISO.

### EDP-03: Data Loss Prevention (DLP)
- Emails or cloud uploads containing PII (SSN, Credit Card, Passport) or proprietary source code are blocked automatically by Microsoft Purview DLP.
