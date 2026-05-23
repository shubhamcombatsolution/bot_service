from . import db
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

class WorkflowTrigger(db.Model):
    __tablename__ = "tbl_workflow_triggers"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bot_id = db.Column(db.Integer, nullable=False)
    tenant_id = db.Column(db.Integer, nullable=False)
    flow_id = db.Column(db.Integer, nullable=False)

    trigger_node_id = db.Column(db.String(255), nullable=False)  
    trigger_type = db.Column(db.String(100), nullable=False)  # "gmail", "webhook", "cron", etc.

    schedule_meta = db.Column(JSONB, nullable=True)  # repeat mode, hour, minute, weekday
    filter_meta = db.Column(JSONB, nullable=True)    # gmail filters (subject, query, readStatus, labelIds...)

    raw_trigger_json = db.Column(JSONB, nullable=False)  # original full formData (future proof)

    status = db.Column(db.String(50), default="active")  # active / paused / deleted
    last_execution_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    next_run_at = db.Column(db.DateTime, nullable=True)

