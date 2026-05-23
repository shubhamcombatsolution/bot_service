from . import db

class RelatedTools(db.Model):
    __tablename__ = 'tbl_related_tools'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys pointing to the main Tools table
    tool_id = db.Column(db.Integer, db.ForeignKey('tbl_tools.tool_id', ondelete='CASCADE'), nullable=False)
    related_tool_id = db.Column(db.Integer, db.ForeignKey('tbl_tools.tool_id', ondelete='CASCADE'), nullable=False)
    
    # Optional: a type or relationship description
    relationship_type = db.Column(db.String(100), nullable=True)
    
    # Timestamp columns
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())
    
    # Optional: soft delete flag
    del_flg = db.Column(db.Boolean, default=False, nullable=False)
    
    # Define relationships (optional, useful in SQLAlchemy ORM)
    tool = db.relationship('Tools', foreign_keys=[tool_id], backref='related_tools')
    related_tool = db.relationship('Tools', foreign_keys=[related_tool_id])
