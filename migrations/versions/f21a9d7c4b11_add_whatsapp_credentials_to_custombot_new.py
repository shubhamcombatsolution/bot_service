"""add whatsapp_credentials column to tbl_custombot_new

Revision ID: f21a9d7c4b11
Revises: c3d9f4b1a2e7
Create Date: 2026-05-10 00:00:00

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "f21a9d7c4b11"
down_revision = "c3d9f4b1a2e7"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'tbl_custombot_new'
              AND column_name = 'whatsapp_credentials'
          ) THEN
            ALTER TABLE tbl_custombot_new
            ADD COLUMN whatsapp_credentials JSONB;
          END IF;
        END $$;
        """
    )


def downgrade():
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'tbl_custombot_new'
              AND column_name = 'whatsapp_credentials'
          ) THEN
            ALTER TABLE tbl_custombot_new
            DROP COLUMN whatsapp_credentials;
          END IF;
        END $$;
        """
    )
