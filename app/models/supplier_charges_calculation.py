from datetime import datetime
from . import db

class SupplierChargesCalculation(db.Model):
    __tablename__ = "supplier_charges_calculation"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    supplier_quotation_id = db.Column(db.String(4), db.ForeignKey("supplier_quotations_new.supplier_quotation_id"), nullable=False, unique=True)
    rfq_no = db.Column(db.String(30), nullable=False)
    charges_json = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    supplier_quotation = db.relationship("SupplierQuotation", backref=db.backref("charges_calculation", uselist=False))
