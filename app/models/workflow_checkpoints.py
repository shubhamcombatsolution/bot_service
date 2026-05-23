from . import db
from datetime import datetime

class WorkflowCheckpoint(db.Model):
    __tablename__ = 'workflow_checkpoints'
    
    # Primary Key
    checkpoint_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Core identifiers
    workflow_id = db.Column(db.String(255), nullable=False)
    execution_id = db.Column(db.String(255), nullable=False)
    
    # Stored context (JSON)
    context = db.Column(db.JSON, nullable=False)
    
    # Optional status info
    status = db.Column(db.String(50), default='success')
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint to avoid duplicates for same workflow execution
    __table_args__ = (
        db.UniqueConstraint('workflow_id', 'execution_id', name='uq_workflow_execution'),
    )
