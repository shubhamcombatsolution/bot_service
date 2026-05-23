from . import db

class Tenant(db.Model):
    __tablename__ = 'tbl_tenants'

    tenant_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_name = db.Column(db.String(255), nullable=False)
    tenant_key = db.Column(db.String(255), nullable=False)
    tenant_address = db.Column(db.String(255))
    tenant_emailid = db.Column(db.String(255), unique=True, nullable=False)
    tenant_contact = db.Column(db.String(20))

    custom_bots = db.relationship('CustomBot', backref='associated_tenant', lazy=True)

    tenant_GSTNo = db.Column(db.String(100))
    tenant_PAN = db.Column(db.String(100))
    tenant_role = db.Column(db.String(50))

    tenant_city = db.Column(db.String(100))
    tenant_country = db.Column(db.String(100))
    tenant_postcode = db.Column(db.String(100))
    tenant_status = db.Column(db.String(100), default="Active")

    tenant_plan_id = db.Column(db.Integer, db.ForeignKey('tbl_bot_plans.plan_id'))

    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now(), nullable=False)

    diagrams = db.relationship('BotDiagram', back_populates="tenant")
    chathistory = db.relationship('ChatHistory', back_populates="tenant", cascade="all, delete-orphan")
    lead = db.relationship('Lead', back_populates="tenant", cascade="all, delete-orphan")
    conversations = db.relationship(
        'Conversation',
        back_populates="tenant",
        cascade="all, delete-orphan"
    )
    agents = db.relationship(
        "Agent",
        back_populates="tenant",
        cascade="all, delete-orphan"
    )
    del_flg = db.Column(db.Boolean, default=False)

    # :white_check_mark: Only ONE relationship here
    collaborators = db.relationship(
        "Collaborator",
        backref="tenant",
        cascade="all, delete-orphan"
    )