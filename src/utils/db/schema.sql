CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- section:audit-log:start
CREATE TABLE IF NOT EXISTS audit_log (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp     TIMESTAMPTZ NOT NULL    DEFAULT NOW(),
    session_id    VARCHAR(64) NOT NULL,
    user_id       VARCHAR(64) NOT NULL,
    action_type   VARCHAR(32) NOT NULL,
    action_name   VARCHAR(64) NOT NULL,
    risk_level    VARCHAR(16) NOT NULL,
    hitl_required BOOLEAN     NOT NULL,
    hitl_decision VARCHAR(16),
    status        VARCHAR(16) NOT NULL,
    payload       JSONB,
    result        JSONB,
    reasoning     TEXT,
    previous_hash VARCHAR(64) NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000',
    entry_hash    VARCHAR(64),
    expires_at    TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 days')
);

ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
DROP RULE IF EXISTS audit_log_no_update ON audit_log;
DROP RULE IF EXISTS audit_log_no_delete ON audit_log;
UPDATE audit_log SET expires_at = timestamp + INTERVAL '7 days' WHERE expires_at IS NULL;
ALTER TABLE audit_log ALTER COLUMN expires_at SET DEFAULT (NOW() + INTERVAL '7 days');
ALTER TABLE audit_log ALTER COLUMN expires_at SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_session ON audit_log (session_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log (user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_expiry ON audit_log (expires_at);

CREATE RULE audit_log_no_update AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
-- section:audit-log:end

-- section:tickets:start
CREATE TABLE IF NOT EXISTS tickets (
    id VARCHAR(64) PRIMARY KEY,
    title TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    priority VARCHAR(32) NOT NULL DEFAULT 'medium',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
-- section:tickets:end
