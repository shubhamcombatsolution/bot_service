from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

class RfqMaterialDetails(db.Model):
    __tablename__ = 'rfq_material_details'
    
    # Primary Key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ✅ RFQ Header Information
    rfq_no = db.Column(db.String(50), nullable=False, unique=True)          # RFQ Number
    requested_by = db.Column(db.String(100), nullable=True)                 # User name who requested
    user_email = db.Column(db.String(150), nullable=True)                   # Email of requester
    date_created = db.Column(db.DateTime, default=db.func.now(), nullable=False)  # RFQ creation date
    required_delivery_date = db.Column(db.Date, nullable=True)              # When material is needed
    lead_time_required_days = db.Column(db.Integer, nullable=True)          # Required lead time threshold
    total_required_quantity = db.Column(db.Numeric(10,2), nullable=True)    # Total qty required
    
    # ✅ Material Details
    uom = db.Column(db.String(50), nullable=True)                           # Unit of measurement
    material_description = db.Column(db.Text, nullable=True)                # Description of material/items
    make_preferred = db.Column(db.String(100), nullable=True)               # Preferred make or brand
    notes = db.Column(db.Text, nullable=True)                               # Additional notes
    
    # ✅ Legacy fields (kept only if needed)
    req_received_date = db.Column(db.Date, nullable=True)                   # Requirement Received Date
    
    # ✅ Status
    status = db.Column(db.String(30), nullable=True, default="rfq_send")     # RFQ status
    
    # ✅ Metadata
    created_at = db.Column(db.DateTime, default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now(), nullable=False)

    def __repr__(self):
        return f"<RfqMaterialDetails RFQ={self.rfq_no}>"
