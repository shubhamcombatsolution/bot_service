from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class SupplierQuotations(db.Model):
    __tablename__ = 'supplier_quotations'

    # Primary Key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Foreign and identifying fields
    rfq_no = db.Column(db.String(100), nullable=False)                 # Reference to RFQ master
    supplier_email = db.Column(db.String(255), nullable=False)         # Supplier unique email
    supplier_name = db.Column(db.String(255), nullable=False)          # Supplier name

    # Quotation details (now stored as string to allow mixed values like '100 Pcs', 'INR 15.00')
    quotation_file_path = db.Column(db.String(500), nullable=True)     # Stored PDF file path
    lead_time_days = db.Column(db.String(50), nullable=True)           # e.g., '2 days'
    offered_quantity = db.Column(db.String(100), nullable=True)        # e.g., '100 Pcs'
    unit_price = db.Column(db.String(100), nullable=True)              # e.g., 'INR 15.00'
    currency = db.Column(db.String(10), nullable=True, default='INR')  # Currency code
    margin = db.Column(db.Numeric(precision=10, scale=2), nullable=True)

    # Status and evaluation
    status = db.Column(db.String(30), nullable=True, default='Pending')  
    evaluation_reason = db.Column(db.Text, nullable=True)                # LLM evaluation comments
    notified = db.Column(db.Boolean, nullable=False, default=False)      # Whether supplier was notified
    remarks = db.Column(db.Text, nullable=True) 
    margin_amount = db.Column(db.Float, nullable=True)
    total_amount = db.Column(db.Float, nullable=True) 
    final_amount = db.Column(db.Float, nullable=True)  
    selected = db.Column(db.Boolean, nullable=False, default=False)       # Whether quotation was selected

    # Audit fields
    last_updated = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<SupplierQuotations {self.rfq_no} - {self.supplier_name}>"
