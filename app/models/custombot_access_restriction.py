from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import VARCHAR
from . import db  

class CustomBotAccessRestriction(db.Model):
    __tablename__ = "tbl_custombot_access_restriction"

    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_custombot_new.bot_id", ondelete="CASCADE"),
        nullable=False
    )
    allowed_ip = db.Column(VARCHAR(45), nullable=True)
    allowed_domain = db.Column(VARCHAR(255), nullable=True)
    created_at = db.Column(db.DateTime, server_default=func.now())
    bot = db.relationship("CustomBotNew", back_populates="access_restrictions")