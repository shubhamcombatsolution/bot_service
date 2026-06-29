"""Add agent_config to tbl_custombot_new

Revision ID: add_agent_config_001
Revises:
Create Date: 2026-06-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_agent_config_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'tbl_custombot_new',
        sa.Column('agent_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=None)
    )


def downgrade():
    op.drop_column('tbl_custombot_new', 'agent_config')
