from . import db

class ToolAuthorization(db.Model):
    __tablename__ = "tbl_tool_authorization"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tbl_tenants.tenant_id"), nullable=False)
    tool_name = db.Column(db.String(100), nullable=False)
    token_json = db.Column(db.JSON, nullable=True)
    
    # New fields
    tool_type = db.Column(db.String(50), default="local", nullable=False)
    mcp_url = db.Column(db.String(255), nullable=True)
    mcp_json = db.Column(db.JSON, nullable=True)

    del_flag = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
