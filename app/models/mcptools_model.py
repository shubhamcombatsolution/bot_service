from . import db

class McpTool(db.Model):
    __tablename__ = 'tbl_mcptools'
    
    tool_id = db.Column(db.Integer, primary_key=True)
    tool_name = db.Column(db.String(255), nullable=False)
    tool_description = db.Column(db.Text, nullable=True)
    tool_logo = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())
    del_flg = db.Column(db.Boolean, nullable=False, default=False)

    def serialize(self):
        """Convert model to dictionary (for JSON responses)"""
        return {
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "tool_description": self.tool_description,
            "tool_logo": self.tool_logo,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "del_flg": self.del_flg,
        }
