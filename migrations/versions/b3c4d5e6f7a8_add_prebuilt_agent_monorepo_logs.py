"""add tbl_prebuilt_agent_monorepo_logs table

Revision ID: b3c4d5e6f7a8
Revises: 7d1f2c9a4b31
Create Date: 2026-05-26 00:00:00
"""
from alembic import op


revision = "b3c4d5e6f7a8"
down_revision = "7d1f2c9a4b31"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_prebuilt_agent_monorepo_logs (
            id                  SERIAL PRIMARY KEY,
            prebuilt_agent_id   INTEGER NOT NULL
                                    REFERENCES tbl_prebuilt_agents(prebuilt_agent_id)
                                    ON DELETE CASCADE,
            action              VARCHAR(20)  NOT NULL DEFAULT 'create',
            status              VARCHAR(20)  NOT NULL,
            triggered_by        INTEGER,
            http_status_code    INTEGER,
            request_payload     JSONB,
            response_body       TEXT,
            error_message       TEXT,
            duration_ms         FLOAT,
            monorepo_url        VARCHAR(512),
            triggered_at        TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_monorepo_logs_agent "
        "ON tbl_prebuilt_agent_monorepo_logs(prebuilt_agent_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_monorepo_logs_triggered_at "
        "ON tbl_prebuilt_agent_monorepo_logs(triggered_at DESC);"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_monorepo_logs_triggered_at;")
    op.execute("DROP INDEX IF EXISTS idx_monorepo_logs_agent;")
    op.execute("DROP TABLE IF EXISTS tbl_prebuilt_agent_monorepo_logs;")
