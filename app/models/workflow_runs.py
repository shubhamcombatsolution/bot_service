from . import db
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime


class WorkflowRun(db.Model):
    __tablename__ = "tbl_workflow_runs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    bot_id = db.Column(db.Integer, nullable=False)
    tenant_id = db.Column(db.Integer, nullable=False)
    
    # This ties the run to a specific workflow version stored in BotDiagram
    diagram_id = db.Column(db.Integer, nullable=False) 

    # Status of execution
    status = db.Column(db.String(50), nullable=False, default="running")
    # running | waiting | completed | failed | cancelled

    # Trigger metadata
    trigger_type = db.Column(db.String(100), nullable=True)  # gmail, webhook, cron, manual
    trigger_id = db.Column(db.Integer, nullable=True)        # FK to tbl_workflow_triggers (optional but useful)

    # Runtime storage for workflow state (outputs, memory, variables, gmail payload, etc.)
    context_json = db.Column(JSONB, nullable=True)
    trigger_data = db.Column(JSONB, nullable=True)

    # For wait/resume — executor stores which node paused the workflow
    current_node_id = db.Column(db.String(255), nullable=True)

    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
