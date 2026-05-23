"""Make workflow run bot_id nullable

Revision ID: ab12cd34ef56
Revises: 5c9b45ed55e5
Create Date: 2026-04-21 00:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ab12cd34ef56"
down_revision = "5c9b45ed55e5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tbl_workflow_runs", schema=None) as batch_op:
        batch_op.alter_column(
            "bot_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade():
    with op.batch_alter_table("tbl_workflow_runs", schema=None) as batch_op:
        batch_op.alter_column(
            "bot_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
