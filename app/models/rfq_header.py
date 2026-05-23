import random
from datetime import datetime
from . import db

class RfqHeader(db.Model):
    __tablename__ = "rfq_header"

    sys_rfq_id = db.Column(db.String(30), primary_key=True)

    customer_rfq_number = db.Column(db.String(100))
    customer_company_name = db.Column(db.String(255))
    customer_name = db.Column(db.String(255))
    customer_email = db.Column(db.String(255))
    rfq_date = db.Column(db.Date)
    due_date = db.Column(db.DateTime)
    currency = db.Column(db.String(10))
    delivery_address = db.Column(db.Text)
    rfq_file_path = db.Column(db.Text)
    notes = db.Column(db.Text)

    customer_address = db.Column(db.Text, nullable=True)
    delivery_address = db.Column(db.Text, nullable=True)
    delivery_pincode = db.Column(db.String(20), nullable=True)
    delivery_country = db.Column(db.String(100), nullable=True)
    
    status = db.Column(
        db.String(30),
        nullable=False,
        default="Pending",
    )

    
    finalized_quotation_json = db.Column(db.JSON, nullable=True)
    finalized_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    deleted_flag = db.Column(db.Boolean, default=False)

    line_items = db.relationship(
        "RfqLineItems",
        backref="header",
        cascade="all, delete-orphan",
        lazy=True
    )
    

    def __repr__(self):
        return f"<RFQ {self.sys_rfq_id}>"
