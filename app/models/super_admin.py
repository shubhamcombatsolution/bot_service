from . import db

class SuperAdmin(db.Model):
    __tablename__ = 'tbl_superadmin'
    
    # Primary Key
    superadmin_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # SuperAdmin-specific fields
    superadmin_username = db.Column(db.String(255), nullable=False, unique=True)
    superadmin_email = db.Column(db.String(255), nullable=False, unique=True)
    superadmin_password = db.Column(db.String(255), nullable=False)  # Store hashed password
    
    # Timestamp fields
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, default=db.func.now(), onupdate=db.func.now())
    
    # Logical deletion flag
    del_flg = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f"<SuperAdmin {self.superadmin_username}>"
