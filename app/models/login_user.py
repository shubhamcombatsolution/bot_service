from . import db
import uuid

class LoginUser(db.Model):
    __tablename__ = 'tbl_loginuser'
    login_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fullname = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, default=None)
    account_name = db.Column(db.String(255), unique=True, default=None)
    api_key = db.Column(db.String(36), unique=True, nullable=True)
    reset_token_hash = db.Column(db.String(255), default=None)  # Adjusted length for clarity
    reset_expires_at = db.Column(db.DateTime, default=None)  # Changed to db.DateTime
    # Ensure 'created_at' column has a default value of the current timestamp
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    # Ensure 'updated_at' column automatically updates with the current timestamp when modified
    updated_at = db.Column(db.DateTime, nullable=False, default=db.func.now(), onupdate=db.func.now())
    
    tenant_id = db.Column(db.Integer, db.ForeignKey('tbl_tenants.tenant_id'), nullable=True)
    role = db.Column(db.String(100), default=None)
    del_flg = db.Column(db.Boolean, default=False)

    def generate_api_key(self):
        """Generate a new API key for the user."""
        self.api_key = str(uuid.uuid4())  # Generate a UUID as the API key
        return self.api_key