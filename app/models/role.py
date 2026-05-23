from . import db

class Role(db.Model):
    __tablename__ = 'tbl_roles'
    role_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    role_name = db.Column(db.String(100), nullable=False, unique=True)
    role_description = db.Column(db.Text, nullable=False)
      # Ensure 'created_at' column has a default value of the current timestamp
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    # Ensure 'updated_at' column automatically updates with the current timestamp when modified
    updated_at = db.Column(db.DateTime, nullable=False, default=db.func.now(), onupdate=db.func.now())
    
    del_flg = db.Column(db.Boolean, default=False)