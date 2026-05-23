from . import db

class BotPlan(db.Model):
    __tablename__ = 'tbl_bot_plans'

    plan_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    plan_name = db.Column(db.String(255), nullable=False)
    plan_description = db.Column(db.Text)
    plan_price = db.Column(db.DECIMAL(10, 2), nullable=False)
    plan_duration = db.Column(db.Integer, nullable=False)
    plan_status = db.Column(db.Boolean, default=True)
    # Define 'payment_status' field as Enum or String
    payment_status = db.Column(db.String(50), nullable=False, default="pending", server_default="pending")  # Example using String
    plan_messages = db.Column(db.Integer, nullable=False, comment="Maximum messages included in the plan")
    no_bot = db.Column(db.Integer, nullable=False, comment="Number of bots allowed")
    no_agent = db.Column(db.Integer, nullable=False, comment="Number of agents allowed")
    message_rollover = db.Column(db.Boolean, nullable=False, default=False)
    overage_limit = db.Column(db.Integer, nullable=True, default=None, comment="Extra messages allowed beyond limit")

    # Ensure 'created_at' column has a default value of the current timestamp
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    tenants_plan = db.relationship('Tenant', backref='tenant_plan', lazy=True)
    
    # Ensure 'updated_at' column automatically updates with the current timestamp when modified
    updated_at = db.Column(db.DateTime, nullable=False, default=db.func.now(), onupdate=db.func.now())
    
    del_flg = db.Column(db.Boolean, default=None)

    # Relationships
    subscriptions = db.relationship('TenantSubscription', backref='plan', lazy=True)
