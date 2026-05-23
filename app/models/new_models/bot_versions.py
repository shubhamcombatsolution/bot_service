from .. import db


class BotVersion(db.Model):
    __tablename__ = "tbl_bot_versions"

    version_id     = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bot_id         = db.Column(db.Integer, db.ForeignKey("tbl_custombot_new.bot_id"), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    is_live        = db.Column(db.Boolean, default=False, nullable=False)
    snapshot       = db.Column(db.JSON, nullable=False)
    snapshot_hash = db.Column(db.String(64), nullable=False)
    published_at   = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    published_by   = db.Column(db.Integer, db.ForeignKey("tbl_tenants.tenant_id"), nullable=True)

    def __repr__(self):
        return f"<BotVersion bot_id={self.bot_id} v{self.version_number} live={self.is_live}>"