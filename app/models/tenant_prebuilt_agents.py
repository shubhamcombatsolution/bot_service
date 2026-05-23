"""
tenant_prebuilt_agents.py

Model for tbl_tenant_prebuilt_agents - tracks which tenants have access to prebuilt agents
"""

from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.models import db


class TenantPrebuiltAgents(db.Model):
    __tablename__ = 'tbl_tenant_prebuilt_agents'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey('tbl_tenants.tenant_id', ondelete='CASCADE'), nullable=False)
    prebuilt_agent_id = Column(Integer, ForeignKey('tbl_prebuilt_agents.prebuilt_agent_id', ondelete='CASCADE'), nullable=False)
    
    # Cloned agent reference
    agent_id = Column(Integer, ForeignKey('tbl_agents.agent_id', ondelete='SET NULL'))
    
    # Status tracking
    status = Column(String(20), default='pending_tools')  # pending_tools, ready, active, inactive
    
    # Missing tools (updated dynamically)
    missing_tools = Column(JSONB, default=[])
    
    # Audit
    granted_at = Column(TIMESTAMP, server_default=func.now())
    activated_at = Column(TIMESTAMP)
    last_checked_at = Column(TIMESTAMP)
    
    def to_dict(self):
        """Serialize to dictionary"""
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'prebuilt_agent_id': self.prebuilt_agent_id,
            'agent_id': self.agent_id,
            'status': self.status,
            'missing_tools': self.missing_tools or [],
            'granted_at': self.granted_at.isoformat() if self.granted_at else None,
            'activated_at': self.activated_at.isoformat() if self.activated_at else None,
            'last_checked_at': self.last_checked_at.isoformat() if self.last_checked_at else None,
        }