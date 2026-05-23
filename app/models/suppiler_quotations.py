from datetime import datetime
from . import db
import random
import string

def short_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))


class SupplierQuotation(db.Model):
    __tablename__ = "supplier_quotations_new"

    # Short Primary Key (4 chars)
    supplier_quotation_id = db.Column(
        db.String(4),
        primary_key=True,
        default=short_id
    )

    # REQUIRED
    sys_rfq_id = db.Column(
        db.String(30),
        db.ForeignKey("rfq_header.sys_rfq_id"),
        nullable=False
    )
    supplier_name = db.Column(db.String(255), nullable=False)

    # OPTIONAL – Supplier
    supplier_email = db.Column(db.String(255))
    supplier_country = db.Column(db.String(100))

    # OPTIONAL – RFQ
    customer_rfq_number = db.Column(db.String(100))

    # OPTIONAL – Currency
    supplier_currency = db.Column(db.String(10))
    exchange_rate = db.Column(db.Numeric(12, 6))

    # OPTIONAL – Delivery (stored in SAME TABLE)
    local_delivery_partner = db.Column(db.String(255))
    local_delivery_partner_type = db.Column(db.String(50))     # bike / van / truck

    freight_delivery_partner = db.Column(db.String(255))
    freight_delivery_partner_type = db.Column(db.String(50))   # air / sea / road

    # OPTIONAL – Flags & status
    accessible_dangerous_goods = db.Column(db.Boolean)
    status = db.Column(db.String(30), default="Pending")
    remarks = db.Column(db.Text)

    # OPTIONAL – File
    quotation_file_path = db.Column(db.String(500))
    
    is_finalized = db.Column(db.Boolean, default=False)
    finalized_at = db.Column(db.DateTime, nullable=True)

    # 🔥 JSON SNAPSHOT (supplier-level)
    finalized_json = db.Column(db.JSON, nullable=True)

    # AUDIT
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # RELATIONSHIP
    line_items = db.relationship(
        "SupplierQuotationLineItem",
        backref="quotation",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<SupplierQuotation {self.supplier_quotation_id} - {self.supplier_name}>"
