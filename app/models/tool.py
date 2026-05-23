from . import db

class Tools(db.Model):
    __tablename__ = 'tbl_tools'
    
    tool_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tool_name = db.Column(db.String(100), nullable=False)
    tool_description = db.Column(db.Text, nullable=False)
    
    # Storing the image file path as a string
    tool_logo = db.Column(db.String(255), nullable=True)  
    tool_class = db.Column(db.String(255), nullable=True)
    
    # Timestamp columns
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())
    
    del_flg = db.Column(db.Boolean, default=False, nullable=False)
