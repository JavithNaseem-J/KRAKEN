"""Initial AKEA Database Schema Migration

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-08-09 10:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        session_id VARCHAR(128) NOT NULL,
        user_id VARCHAR(128) NOT NULL,
        action_type VARCHAR(32) NOT NULL,
        action_name VARCHAR(128) NOT NULL,
        risk_level VARCHAR(32) NOT NULL,
        hitl_required BOOLEAN NOT NULL DEFAULT FALSE,
        hitl_decision VARCHAR(32),
        status VARCHAR(32) NOT NULL,
        reasoning TEXT,
        payload JSONB,
        result JSONB,
        previous_hash CHAR(64),
        entry_hash CHAR(64)
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log;")
