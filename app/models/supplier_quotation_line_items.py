from datetime import datetime
from . import db
import random
import string

def short_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

class SupplierQuotationLineItem(db.Model):
    __tablename__ = "supplier_quotation_line_items"

    # Short Primary Key (4 chars)
    supplier_line_item_id = db.Column(
        db.String(4),
        primary_key=True,
        default=short_id
    )

    # REQUIRED
    supplier_quotation_id = db.Column(
        db.String(4),
        db.ForeignKey("supplier_quotations_new.supplier_quotation_id"),
        nullable=False
    )

    # OPTIONAL – RFQ Mapping
    rfq_line_id = db.Column(
        db.String(50),
        db.ForeignKey("rfq_line_items.rfq_line_id")
    )

    # OPTIONAL – Material
    material_no = db.Column(db.String(200))
    material_description = db.Column(db.Text)

    # OPTIONAL – Commercials
    offered_quantity = db.Column(db.Numeric(18, 3))
    price_per_unit = db.Column(db.Numeric(18, 4))
    lead_time = db.Column(db.String(50))

    # OPTIONAL – Compliance & packaging
    hsn_code = db.Column(db.String(50))
    weight_of_package = db.Column(db.String(50))
    dim_of_package = db.Column(db.String(50))
    
    # 🔥 FINALIZATION FLAGS
    is_selected = db.Column(db.Boolean, default=False)
    finalized_quantity = db.Column(db.Numeric(18, 3), nullable=True)

    # AUDIT
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    def __repr__(self):
        return f"<SupplierQuotationLineItem {self.material_no}>"
