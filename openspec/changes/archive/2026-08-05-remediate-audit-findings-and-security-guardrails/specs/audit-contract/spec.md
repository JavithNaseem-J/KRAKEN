# audit-contract Specification

## Purpose
Delta spec for SHA-256 cryptographic hash chaining on append-only audit records.

## Requirements

### Requirement: Audit log entries form a SHA-256 cryptographic hash chain
The Audit service `AuditStore` in `services/audit/audit_store.py` SHALL store a `previous_hash` column for every entry in `audit_log`. The `entry_hash` SHALL be calculated as `SHA256(previous_hash + timestamp + action_name + session_id + payload_json)`. If no previous record exists in `audit_log`, `previous_hash` SHALL default to `0` * 64 (`0000000000000000000000000000000000000000000000000000000000000000`).

#### Scenario: Audit entry inserted with hash chain linkage
- **WHEN** a new action execution is logged via `audit_store.log_action(...)`
- **THEN** the entry fetches the latest `entry_hash` from the table as `previous_hash`, computes its own `entry_hash`, and commits both columns to PostgreSQL

#### Scenario: Audit chain integrity verification passes
- **WHEN** an audit verification script inspects the `audit_log` table
- **THEN** each row's `previous_hash` matches the preceding row's `entry_hash`, proving the log sequence is intact
