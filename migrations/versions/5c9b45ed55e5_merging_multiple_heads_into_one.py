"""Merging multiple heads into one

Revision ID: 5c9b45ed55e5
Revises: 
Create Date: 2025-03-12 12:42:39.061162

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5c9b45ed55e5'
down_revision = ('2b09e784453d', '6667bafe7c7e', 'da42392b181d')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
