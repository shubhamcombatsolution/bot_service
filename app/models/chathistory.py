from . import db

class ChatHistory(db.Model):
    __tablename__ = 'tbl_chathistory'

    chathistory_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tbl_tenants.tenant_id'), nullable=False)
    bot_id = db.Column(
        db.Integer,
        db.ForeignKey('tbl_custombot_new.bot_id'),
        nullable=False
    )
    session_id = db.Column(db.String, nullable=False)
    query = db.Column(db.String, nullable=False)
    response = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    # Relationships
    tenant = db.relationship('Tenant', back_populates="chathistory")
    bot = db.relationship(
        'CustomBotNew',
        back_populates="chathistory"
    )
    
    @staticmethod
    def bot_exists(bot_id: int, session) -> bool:
        """Check if a bot with the given ID exists."""
        from .new_models.custom_bot import CustomBotNew
        return session.query(CustomBotNew).filter_by(bot_id=bot_id).first() is not None