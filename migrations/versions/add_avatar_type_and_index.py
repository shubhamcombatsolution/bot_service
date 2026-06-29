"""Add avatar_type and avatar_index columns to tbl_custombot_new

Revision ID: avatar_type_index_001
Revises:
Create Date: 2026-06-03 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'avatar_type_index_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add avatar_type column
    op.add_column('tbl_custombot_new', sa.Column('avatar_type', sa.String(20), nullable=True, server_default='file'))

    # Add avatar_index column
    op.add_column('tbl_custombot_new', sa.Column('avatar_index', sa.Integer(), nullable=True))


def downgrade():
    # Remove avatar_index column
    op.drop_column('tbl_custombot_new', 'avatar_index')

    # Remove avatar_type column
    op.drop_column('tbl_custombot_new', 'avatar_type')
