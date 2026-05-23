from datetime import datetime
from . import db

class ContactUs(db.Model):
    __tablename__ = 'tbl_contactus'

    contactus_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)  # Specify max length
    work_mail = db.Column(db.String(150), nullable=False)  # Specify max length for email
    query = db.Column(db.String(500), nullable=False)  # Provide a larger size for queries

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, server_default=db.func.now())

    def __repr__(self):
        return f"<ContactUs(contactus_id={self.contactus_id}, name={self.name}, work_mail={self.work_mail})>"
