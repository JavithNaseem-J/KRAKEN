-- ============================================================
-- AKEA Database Initialisation
-- Runs once when the postgres container first starts.
-- ============================================================

-- pgvector extension (required for long-term memory embeddings)
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
    reasoning     TEXT
);

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

-- ── Structured Ticket History ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tickets (
    id          VARCHAR(64)  PRIMARY KEY,
    title       VARCHAR(512) NOT NULL,
    description TEXT,
    status      VARCHAR(32),
    priority    VARCHAR(16),
    category    VARCHAR(64),
    created_at  TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    metadata    JSONB        NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_tickets_status   ON tickets (status);
CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets (priority);
CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets (category);
