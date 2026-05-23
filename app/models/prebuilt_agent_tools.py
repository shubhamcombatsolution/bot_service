"""
prebuilt_agent_tools.py

Model for tbl_prebuilt_agent_tools - defines tool requirements for prebuilt agents
"""

from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.models import db


class PrebuiltAgentTools(db.Model):
    __tablename__ = 'tbl_prebuilt_agent_tools'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    prebuilt_agent_id = Column(Integer, ForeignKey('tbl_prebuilt_agents.prebuilt_agent_id', ondelete='CASCADE'), nullable=False)
    
    # Tool info
    tool_name = Column(String(50), nullable=False)
    tool_type = Column(String(20), default='local')
    action_tools = Column(JSONB, default=[])
    
    # MCP specific
    mcp_url = Column(String(255))
    
    # Requirement level
    is_required = Column(Boolean, default=True)
    
    # Audit
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    def to_dict(self):
        """Serialize to dictionary"""
        return {
            'id': self.id,
            'prebuilt_agent_id': self.prebuilt_agent_id,
            'tool_name': self.tool_name,
            'tool_type': self.tool_type,
            'action_tools': self.action_tools or [],
            'mcp_url': self.mcp_url,
            'is_required': self.is_required,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }