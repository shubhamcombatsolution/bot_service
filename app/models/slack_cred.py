from . import db


class SlackCred(db.Model):
    __tablename__ = "tbl_slack_cred"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bot_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_custombot_new.bot_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    bot_token = db.Column(db.Text, nullable=True)
    signing_secret = db.Column(db.Text, nullable=True)
    app_token = db.Column(db.Text, nullable=True)
    default_channel_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

