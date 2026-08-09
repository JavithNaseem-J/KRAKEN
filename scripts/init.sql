CREATE EXTENSION IF NOT EXISTS vector;
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

-- Prevent any UPDATE or DELETE on audit_log (append-only enforcement)
CREATE RULE audit_log_no_update AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE RULE audit_log_no_delete AS ON DELETE TO audit_log DO INSTEAD NOTHING;

-- ── Long-term Episodic Memory ─────────────────────────────────────────────────
-- bge-small-en produces 384-dimension embeddings
CREATE TABLE IF NOT EXISTS episodic_memory (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  VARCHAR(64) NOT NULL,
    user_id     VARCHAR(64) NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content     TEXT        NOT NULL,
    embedding   vector(384),
    metadata    JSONB       NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_episodic_memory_embedding
    ON episodic_memory USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);

CREATE INDEX IF NOT EXISTS idx_episodic_memory_user
    ON episodic_memory (user_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_episodic_memory_session
    ON episodic_memory (session_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_session
    ON audit_log (session_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_user
    ON audit_log (user_id, timestamp DESC);
