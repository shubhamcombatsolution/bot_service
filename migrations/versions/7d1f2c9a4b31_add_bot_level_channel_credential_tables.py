"""add bot-level whatsapp/slack credential tables

Revision ID: 7d1f2c9a4b31
Revises: f21a9d7c4b11
Create Date: 2026-05-11 00:00:00
"""
from alembic import op


revision = "7d1f2c9a4b31"
down_revision = "f21a9d7c4b11"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_whatsapp_cred (
            id SERIAL PRIMARY KEY,
            bot_id INTEGER NOT NULL UNIQUE REFERENCES tbl_custombot_new(bot_id) ON DELETE CASCADE,
            phone_number_id VARCHAR(100),
            business_account_id VARCHAR(100),
            access_token TEXT,
            verify_token VARCHAR(255),
            graph_api_version VARCHAR(50) DEFAULT 'v19.0',
            default_recipient_number VARCHAR(30),
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_slack_cred (
            id SERIAL PRIMARY KEY,
            bot_id INTEGER NOT NULL UNIQUE REFERENCES tbl_custombot_new(bot_id) ON DELETE CASCADE,
            bot_token TEXT,
            signing_secret TEXT,
            app_token TEXT,
            default_channel_id VARCHAR(100),
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_whatsapp_cred_bot_id ON tbl_whatsapp_cred(bot_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_slack_cred_bot_id ON tbl_slack_cred(bot_id);")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_slack_cred_bot_id;")
    op.execute("DROP INDEX IF EXISTS idx_whatsapp_cred_bot_id;")
    op.execute("DROP TABLE IF EXISTS tbl_slack_cred;")
    op.execute("DROP TABLE IF EXISTS tbl_whatsapp_cred;")

