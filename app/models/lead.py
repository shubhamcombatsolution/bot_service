from datetime import datetime
from . import db

class Lead(db.Model):
    __tablename__ = 'tbl_leads'

    lead_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tbl_tenants.tenant_id'), nullable=False)  # Added tenant_id
    bot_id = db.Column(db.Integer, db.ForeignKey('tbl_custombot.bot_id'), nullable=False)
    name = db.Column(db.String, nullable=True)
    email = db.Column(db.String, nullable=True)
    contact_number = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    tenant = db.relationship('Tenant', back_populates="lead") 
    bot = db.relationship('CustomBot', back_populates="lead") 

    def __repr__(self):
        return f"<Lead(lead_id={self.lead_id}, name={self.name}, email={self.email})>"
