"""Add completed_step to tbl_custombot_new

Revision ID: add_completed_step_001
Revises:
Create Date: 2026-06-03

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_completed_step_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'tbl_custombot_new',
        sa.Column('completed_step', sa.Integer(), nullable=False, server_default='0')
    )


def downgrade():
    op.drop_column('tbl_custombot_new', 'completed_step')
