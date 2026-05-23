from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from . import db


class WorkflowAgentStepLog(db.Model):
    __tablename__ = "tbl_workflow_agent_step_logs"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    # 🔗 Link to workflow run
    run_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    diagram_id = db.Column(db.Integer, nullable=True, index=True)
    bot_id = db.Column(db.Integer, nullable=True, index=True)


    # 🔗 Node context
    node_id = db.Column(db.String(255), nullable=False, index=True)
    agent_id = db.Column(db.Integer, nullable=False, index=True)

    # 🔥 Step details
    step_index = db.Column(db.Integer, nullable=False)
    step_type = db.Column(db.String(50), nullable=False)
    # llm_start | llm_end | tool_start | tool_end | error | chain_start | chain_end

    tool_name = db.Column(db.String(255), nullable=True)

    status = db.Column(db.String(50), nullable=False)
    # running | completed | failed

    message = db.Column(db.Text, nullable=True)

    # All structured data goes here
    data = db.Column(JSONB, nullable=True)

    log_level = db.Column(db.String(20), default="INFO", index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
