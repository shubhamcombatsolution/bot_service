"""add conversation_key to tbl_conversations for per-sender memory partitioning

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-05-26 00:00:00
"""
from alembic import op


revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE tbl_conversations
        ADD COLUMN IF NOT EXISTS conversation_key VARCHAR(255) DEFAULT NULL;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_key "
        "ON tbl_conversations(tenant_id, agent_id, memory_type, conversation_key);"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_conversations_key;")
    op.execute(
        "ALTER TABLE tbl_conversations DROP COLUMN IF EXISTS conversation_key;"
    )
