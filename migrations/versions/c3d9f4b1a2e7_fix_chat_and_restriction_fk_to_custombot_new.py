"""Fix chat history and access restriction bot_id FKs to tbl_custombot_new

Revision ID: c3d9f4b1a2e7
Revises: ab12cd34ef56
Create Date: 2026-04-27 00:00:00

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "c3d9f4b1a2e7"
down_revision = "ab12cd34ef56"
branch_labels = None
depends_on = None


def upgrade():
    # tbl_chathistory.bot_id -> tbl_custombot_new.bot_id
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'tbl_chathistory_bot_id_fkey'
          ) THEN
            ALTER TABLE tbl_chathistory
            DROP CONSTRAINT tbl_chathistory_bot_id_fkey;
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        ALTER TABLE tbl_chathistory
        ADD CONSTRAINT tbl_chathistory_bot_id_fkey
        FOREIGN KEY (bot_id) REFERENCES tbl_custombot_new(bot_id);
        """
    )

    # tbl_custombot_access_restriction.bot_id -> tbl_custombot_new.bot_id
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'tbl_custombot_access_restriction_bot_id_fkey'
          ) THEN
            ALTER TABLE tbl_custombot_access_restriction
            DROP CONSTRAINT tbl_custombot_access_restriction_bot_id_fkey;
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        ALTER TABLE tbl_custombot_access_restriction
        ADD CONSTRAINT tbl_custombot_access_restriction_bot_id_fkey
        FOREIGN KEY (bot_id) REFERENCES tbl_custombot_new(bot_id)
        ON DELETE CASCADE;
        """
    )


def downgrade():
    # Revert both FKs back to legacy tbl_custombot.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'tbl_chathistory_bot_id_fkey'
          ) THEN
            ALTER TABLE tbl_chathistory
            DROP CONSTRAINT tbl_chathistory_bot_id_fkey;
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        ALTER TABLE tbl_chathistory
        ADD CONSTRAINT tbl_chathistory_bot_id_fkey
        FOREIGN KEY (bot_id) REFERENCES tbl_custombot(bot_id);
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'tbl_custombot_access_restriction_bot_id_fkey'
          ) THEN
            ALTER TABLE tbl_custombot_access_restriction
            DROP CONSTRAINT tbl_custombot_access_restriction_bot_id_fkey;
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        ALTER TABLE tbl_custombot_access_restriction
        ADD CONSTRAINT tbl_custombot_access_restriction_bot_id_fkey
        FOREIGN KEY (bot_id) REFERENCES tbl_custombot(bot_id)
        ON DELETE CASCADE;
        """
    )
