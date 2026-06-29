# app/models/mcp_agent_tools.py

from . import db
from sqlalchemy.ext.mutable import MutableList, MutableDict
from sqlalchemy.dialects.postgresql import JSONB


class McpAgentTools(db.Model):
    __tablename__ = "tbl_mcp_agent_tools"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_tenants.tenant_id"),
        nullable=False
    )

    agent_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_agents.agent_id"),
        nullable=True
    )

    mcp_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_mcp_tools.id"),
        nullable=True
    )

    tool_name = db.Column(db.String(255), nullable=False)
    mcp_url = db.Column(db.String(255), nullable=True)

    # 'local'      → Python class via /local_tool/call (GmailTool, CalendarTool, etc.)
    # 'jnanic_mcp' → mcp.jnanic.com via stdio MCP server
    # 'mcp'        → alias for jnanic_mcp (backward compat)
    # 'external'   → direct HTTP call to external URL
    tool_type = db.Column(db.String(20), nullable=False, default="mcp")

    tool_config = db.Column(
        MutableDict.as_mutable(JSONB),
        default=dict
    )

    action_tools = db.Column(
        MutableList.as_mutable(JSONB),
        default=list
    )

    action_tools_description = db.Column(
        MutableList.as_mutable(JSONB),
        default=list
    )

    del_flag = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False
    )

    agent = db.relationship("Agent", backref="mcp_tools")
    mcp_tool = db.relationship("McpTools", backref="agent_tools")

    def __repr__(self):
        return f"<McpAgentTools id={self.id} tool_name={self.tool_name}>"