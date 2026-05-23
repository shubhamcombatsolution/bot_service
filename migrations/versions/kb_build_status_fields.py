"""Add build status fields to tbl_knowledge_base

Revision ID: kb_build_status_001
Revises: 
Create Date: 2024-12-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'kb_build_status_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Add build status fields to knowledge base table."""
    # Add build_status column
    op.add_column(
        'tbl_knowledge_base',
        sa.Column('build_status', sa.String(50), nullable=True, server_default='pending')
    )
    
    # Add build_task_id column
    op.add_column(
        'tbl_knowledge_base',
        sa.Column('build_task_id', sa.String(100), nullable=True)
    )
    
    # Add build_error column
    op.add_column(
        'tbl_knowledge_base',
        sa.Column('build_error', sa.Text, nullable=True)
    )
    
    # Add build_started_at column
    op.add_column(
        'tbl_knowledge_base',
        sa.Column('build_started_at', sa.DateTime, nullable=True)
    )
    
    # Add build_completed_at column
    op.add_column(
        'tbl_knowledge_base',
        sa.Column('build_completed_at', sa.DateTime, nullable=True)
    )
    
    # Update existing records to have 'completed' status
    op.execute("UPDATE tbl_knowledge_base SET build_status = 'completed' WHERE build_status IS NULL OR build_status = 'pending'")


def downgrade():
    """Remove build status fields from knowledge base table."""
    op.drop_column('tbl_knowledge_base', 'build_completed_at')
    op.drop_column('tbl_knowledge_base', 'build_started_at')
    op.drop_column('tbl_knowledge_base', 'build_error')
    op.drop_column('tbl_knowledge_base', 'build_task_id')
    op.drop_column('tbl_knowledge_base', 'build_status')

