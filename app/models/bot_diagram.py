from . import db

class BotDiagram(db.Model):
    __tablename__ = 'tbl_bot_diagrams'
    
    diagram_id = db.Column(db.Integer, primary_key=True, autoincrement=True, nullable=False)

    # ✅ FIXED
    bot_id = db.Column(
        db.Integer,
        db.ForeignKey('tbl_custombot_new.bot_id'),
        nullable=True
    )

    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tbl_tenants.tenant_id'),
        nullable=False
    )

    diagram_json = db.Column(db.Text, nullable=False)
    workflow_name = db.Column(db.String(255), nullable=True)
    channel = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default="created")

    bot = db.relationship('CustomBotNew', back_populates="diagrams")
    tenant = db.relationship('Tenant', back_populates="diagrams")

    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    del_flg = db.Column(db.Boolean, default=False, nullable=False)