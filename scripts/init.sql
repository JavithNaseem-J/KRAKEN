CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Audit Log (append-only) ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp     TIMESTAMPTZ NOT NULL    DEFAULT NOW(),
    session_id    VARCHAR(64) NOT NULL,
    user_id       VARCHAR(64) NOT NULL,
    action_type   VARCHAR(32) NOT NULL,   -- 'READ' | 'WRITE'
    action_name   VARCHAR(64) NOT NULL,
    risk_level    VARCHAR(16) NOT NULL,   -- 'SAFE' | 'CRITICAL'
    hitl_required BOOLEAN     NOT NULL,
    hitl_decision VARCHAR(16),            -- 'approved'|'rejected'|'timeout'|NULL
    status        VARCHAR(16) NOT NULL,   -- 'success'|'failure'|'cancelled'
    payload       JSONB,
    result        JSONB,
    reasoning     TEXT,
    previous_hash VARCHAR(64) NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000',
    entry_hash    VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_session ON audit_log (session_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log (user_id, timestamp DESC);

-- Prevent any UPDATE or DELETE on audit_log (append-only enforcement)
CREATE RULE audit_log_no_update AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE RULE audit_log_no_delete AS ON DELETE TO audit_log DO INSTEAD NOTHING;

-- ── Ticket Tracking (relational) ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tickets (
    id VARCHAR(64) PRIMARY KEY,
    title TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    priority VARCHAR(32) NOT NULL DEFAULT 'medium',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
