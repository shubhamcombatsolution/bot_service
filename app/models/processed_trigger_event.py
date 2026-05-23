from . import db
from datetime import datetime


class ProcessedTriggerEvent(db.Model):
    __tablename__ = "processed_trigger_events"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    tenant_id = db.Column(db.Integer, nullable=False, index=True)
    trigger_id = db.Column(db.Integer, nullable=False, index=True)

    event_id = db.Column(db.Text, nullable=False)
    event_source = db.Column(db.String(50), nullable=False)

    processed_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "trigger_id",
            "event_id",
            name="uq_trigger_event_once"
        ),
    )
