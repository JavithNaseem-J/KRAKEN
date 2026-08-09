## ADDED Requirements

### Requirement: Audit Hash-Chain Verification Endpoint
The Audit service SHALL provide an endpoint `GET /verify-chain` that verifies the SHA-256 cryptographic hash chain across all recorded audit entries.

#### Scenario: Verifying uncorrupted audit chain
- **WHEN** client sends a request to `GET /verify-chain` on an intact audit store
- **THEN** audit service recomputes all entry hashes and returns status 200 with `valid: true` and verified entry count

#### Scenario: Detecting audit log tampering
- **WHEN** client sends a request to `GET /verify-chain` on a log with modified or missing hashes
- **THEN** audit service returns `valid: false` with the exact sequence ID of the broken hash link
