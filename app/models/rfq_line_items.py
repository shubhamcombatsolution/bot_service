import uuid
from datetime import datetime
from . import db

import random
import string

def short_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

class RfqLineItems(db.Model):
    __tablename__ = "rfq_line_items"

    rfq_line_id = db.Column(db.String(4), nullable=False, unique=True, index=True, default=short_id, primary_key=True,)

    sys_rfq_id = db.Column(db.String(30), db.ForeignKey("rfq_header.sys_rfq_id"), nullable=False)

    customer_part_number = db.Column(db.String(200))

    product_description = db.Column(db.Text)
    quantity = db.Column(db.Numeric(18, 3))
    uom = db.Column(db.String(20))
    lead_time_days = db.Column(db.Integer)
    remarks = db.Column(db.Text)

    mapping_json = db.Column(db.JSON)  # NEW FIELD

    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    deleted_flag = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<RFQ Line Item {self.rfq_line_id}>"
