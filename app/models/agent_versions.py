from . import db
from sqlalchemy.dialects.postgresql import JSONB


class AgentVersion(db.Model):
    __tablename__ = "tbl_agent_versions"

    version_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    agent_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_agents.agent_id"),
        nullable=False,
        index=True
    )

    version_number = db.Column(db.Integer, nullable=False)

    is_live = db.Column(db.Boolean, default=False, nullable=False)

    snapshot = db.Column(JSONB, nullable=False)
    snapshot_hash = db.Column(db.String(64), nullable=False)

    deployed_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    deployed_by = db.Column(
        db.Integer,
        db.ForeignKey("tbl_tenants.tenant_id"),
        nullable=True
    )