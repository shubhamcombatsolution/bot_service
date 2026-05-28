"""
prebuilt_agent_monorepo_log.py

Stores one row per manual "Send to Monorepo" action so the
Super Admin UI can display per-agent sync history.

Table: tbl_prebuilt_agent_monorepo_logs
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from app.models import db


class PrebuiltAgentMonorepoLog(db.Model):
    """
    Audit log for manual monorepo sync events triggered by Super Admin.
    One row is written every time the "Send to Monorepo" button is clicked.
    """
    __tablename__ = "tbl_prebuilt_agent_monorepo_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Which agent was synced
    prebuilt_agent_id = Column(
        Integer,
        ForeignKey("tbl_prebuilt_agents.prebuilt_agent_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "create" | "update" | "delete"
    action = Column(String(20), nullable=False, default="create")

    # "success" | "failed"
    status = Column(String(20), nullable=False)

    # Super Admin user_id who clicked the button
    triggered_by = Column(Integer, nullable=True)

    # HTTP response code from monorepo (NULL if request never reached the server)
    http_status_code = Column(Integer, nullable=True)

    # Payload that was POSTed to the monorepo endpoint
    request_payload = Column(JSONB, nullable=True)

    # First 2 000 chars of the monorepo response body
    response_body = Column(Text, nullable=True)

    # Exception / connection error message (only when status="failed")
    error_message = Column(Text, nullable=True)

    # Wall-clock duration of the HTTP call in milliseconds
    duration_ms = Column(Float, nullable=True)

    # Monorepo target URL used for this call
    monorepo_url = Column(String(512), nullable=True)

    triggered_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "prebuilt_agent_id": self.prebuilt_agent_id,
            "action": self.action,
            "status": self.status,
            "triggered_by": self.triggered_by,
            "http_status_code": self.http_status_code,
            "request_payload": self.request_payload,
            "response_body": self.response_body,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "monorepo_url": self.monorepo_url,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
        }
