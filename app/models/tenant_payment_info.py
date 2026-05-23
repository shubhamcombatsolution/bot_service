#tenant_payment_info.py

from . import db

class tenant_payment_info(db.Model):
    __tablename__ = 'tbl_payment_info'

    intent_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    razorpay_order_id = db.Column(db.String(255), nullable=False)
    razorpay_payment_id = db.Column(db.String(255), nullable=False)
    razorpay_signature = db.Column(db.String(255), nullable=True)
    Paid_amount = db.Column(db.Integer, default=1024)
    plans = db.Column(db.String(255), nullable=False)          #simple,silver,golden
    payment_mode = db.Column(db.String(255), nullable=False)   #monthly/yearly
    from_date = db.Column(db.String(255), nullable=False)
    end_date = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    del_flg = db.Column(db.Boolean, default=False)
    # Foreign key reference to tbl_tenants.tenant_id
    tenant_id = db.Column(db.Integer, db.ForeignKey('tbl_tenants.tenant_id'), nullable=False)
    status = db.Column(db.String(255), nullable=False)
    # Relationship to Tenant model
    tenant = db.relationship('Tenant', backref=db.backref('payments', lazy=True, cascade='all, delete-orphan'))
    