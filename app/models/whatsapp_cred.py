from . import db


class WhatsAppCred(db.Model):
    __tablename__ = "tbl_whatsapp_cred"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bot_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_custombot_new.bot_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    phone_number_id = db.Column(db.String(100), nullable=True)
    business_account_id = db.Column(db.String(100), nullable=True)
    access_token = db.Column(db.Text, nullable=True)
    verify_token = db.Column(db.String(255), nullable=True)
    graph_api_version = db.Column(db.String(50), nullable=True, default="v19.0")
    default_recipient_number = db.Column(db.String(30), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

