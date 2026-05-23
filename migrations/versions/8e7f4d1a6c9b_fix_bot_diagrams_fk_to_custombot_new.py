"""Fix tbl_bot_diagrams bot_id foreign key to point at tbl_custombot_new

Revision ID: 8e7f4d1a6c9b
Revises: fb5978788e95
Create Date: 2026-04-18 03:00:00

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "8e7f4d1a6c9b"
down_revision = "fb5978788e95"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tbl_bot_diagrams", schema=None) as batch_op:
        batch_op.drop_constraint("tbl_bot_diagrams_bot_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "tbl_bot_diagrams_bot_id_fkey",
            "tbl_custombot_new",
            ["bot_id"],
            ["bot_id"],
        )


def downgrade():
    with op.batch_alter_table("tbl_bot_diagrams", schema=None) as batch_op:
        batch_op.drop_constraint("tbl_bot_diagrams_bot_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "tbl_bot_diagrams_bot_id_fkey",
            "tbl_custombot",
            ["bot_id"],
            ["bot_id"],
        )
