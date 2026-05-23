"""
Database model for Wait Node states
Stores paused workflow execution state
"""
from datetime import datetime
from sqlalchemy import Index
from . import db


class WorkflowWaitState(db.Model):
    __tablename__ = "workflow_wait_states"

    # Primary key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Identifiers
    workflow_run_id = db.Column(db.Integer, nullable=False, index=True)
    execution_id = db.Column(db.String(100), nullable=False, index=True)
    bot_id = db.Column(db.String(50), nullable=False)
    tenant_id = db.Column(db.String(50), nullable=False)
    diagram_id = db.Column(db.Integer, nullable=False)
    node_id = db.Column(db.String(100), nullable=False)
    trigger_id = db.Column(db.Integer, nullable=True)  # Link to workflow_trigger if applicable

    # Wait Node Configuration (from node config)
    webhook_url = db.Column(db.Text, nullable=False)
    success_path = db.Column(db.String(200), nullable=False, default="status")
    success_value = db.Column(db.JSON, nullable=True)  # bool | string | number
    backoff_minutes = db.Column(db.JSON, nullable=False)  # [1, 2, 5, 10...]
    max_retries = db.Column(db.Integer, nullable=False, default=5)
    fetch_url_on_success = db.Column(db.Text, nullable=True)
    headers = db.Column(db.JSON, nullable=True)
    timeout_at = db.Column(db.DateTime, nullable=False)
    
    tracking_key = db.Column(db.String(255), nullable=False, index=True)
    tracking_type = db.Column(db.String(50), nullable=False, index=True)


    # Current State
    status = db.Column(
        db.String(20),
        nullable=False,
        default="waiting",
        index=True
    )  # waiting | completed | failed | timeout

    retry_count = db.Column(db.Integer, nullable=False, default=0)
    next_poll_at = db.Column(db.DateTime, nullable=False, index=True)

    # Workflow Context
    workflow_state = db.Column(db.JSON, nullable=False)
    last_response = db.Column(db.JSON, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    completed_at = db.Column(db.DateTime, nullable=True)

    # Indexes
    __table_args__ = (
        Index("idx_wait_polling", "status", "next_poll_at"),
        Index("idx_wait_execution", "workflow_run_id"),
        Index("idx_wait_tenant", "tenant_id", "status"),
    )

    def __repr__(self):
        return (
            f"<WorkflowWaitState("
            f"id={self.id}, "
            f"workflow_run_id={self.workflow_run_id}, "
            f"node_id={self.node_id}, "
            f"status={self.status}, "
            f"retry={self.retry_count}/{self.max_retries}"
            f")>"
        )

    def to_dict(self):
        return {
            "id": self.id,
            "workflow_run_id": self.workflow_run_id,
            "bot_id": self.bot_id,
            "tenant_id": self.tenant_id,
            "diagram_id": self.diagram_id,
            "node_id": self.node_id,
            "webhook_url": self.webhook_url,
            "status": self.status,
            "retry_count": self.retry_count,
            "next_poll_at": self.next_poll_at.isoformat() if self.next_poll_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
        }
