from . import db
from sqlalchemy import Enum

class TenantSubscription(db.Model):
    __tablename__ = 'tbl_tenant_subscriptions'
    subscription_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tbl_tenants.tenant_id'), default=None)
    plan_id = db.Column(db.Integer, db.ForeignKey('tbl_bot_plans.plan_id'), default=None)
    subscription_start = db.Column(db.DateTime, nullable=False)
    subscription_end = db.Column(db.DateTime, nullable=False)
    auto_renewal = db.Column(db.Boolean, default=False)
    subscription_status = db.Column(Enum('active', 'expired', 'suspended', name='subscription_status_enum'), default='active')
    del_flg = db.Column(db.Boolean, default=False)
    remaining_msg = db.Column(db.Integer, default=None)
    total_plan_msg = db.Column(db.Integer, default=None)  # Optional: snapshot of plan_messages at 
    remaining_bots = db.Column(db.Integer, nullable=True, default=None)
    remaining_agent = db.Column(db.Integer, nullable=True, default=None)

    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.now(),
        onupdate=db.func.now()
    )
    # Relationships
    tenant = db.relationship('Tenant', backref='subscriptions', lazy=True)