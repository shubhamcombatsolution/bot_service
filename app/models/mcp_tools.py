from . import db
from sqlalchemy.dialects.postgresql import JSONB

class McpTools(db.Model):
    __tablename__ = "tbl_mcp_tools"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, nullable=False)
    mcp_name = db.Column(db.String(255), nullable=False)
    mcp_url = db.Column(db.String(255), nullable=False)

    mcp_json = db.Column(JSONB, nullable=True)
    mcp_tools = db.Column(JSONB, nullable=True)
    mcp_action_tools = db.Column(JSONB, nullable=True)

    # 'jnanic_mcp' → mcp.jnanic.com / stdio (Jnanic hosted MCP server)
    # 'external'   → remote HTTP/SSE MCP (e.g. Zapier, SerpAPI, custom)
    tool_type = db.Column(db.String(20), nullable=False, default="jnanic_mcp")

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    del_flag = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<McpTools id={self.id} tenant_id={self.tenant_id} name={self.mcp_name}>"
