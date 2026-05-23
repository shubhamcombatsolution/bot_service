from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from . import db

class WorkflowNodeLog(db.Model):
    __tablename__ = "tbl_workflow_node_logs"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    run_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    node_id = db.Column(db.String(255), nullable=False)
    node_type = db.Column(db.String(100), nullable=True)

    event_type = db.Column(
        db.String(50),
        nullable=False
    )
    # started | completed | failed | skipped | retry | cached | timeout

    status = db.Column(db.String(50), nullable=False)

    message = db.Column(db.Text, nullable=True)

    payload = db.Column(JSONB, nullable=True)
    # inputs / outputs / errors / metadata

    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    duration_ms = db.Column(db.Float, nullable=True)
    
    log_level = db.Column(db.String(20),nullable=False,default="INFO",index=True)


    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
