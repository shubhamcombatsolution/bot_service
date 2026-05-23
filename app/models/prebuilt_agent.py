"""
prebuilt_agent.py

SQLAlchemy model for tbl_prebuilt_agents and tbl_tenant_cloned_agents
Manages Super Admin prebuilt agent templates (no credentials stored)
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DECIMAL, TIMESTAMP, ARRAY, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models import db


class PrebuiltAgent(db.Model):
    """
    Super Admin managed agent templates.
    NO credentials stored - tenants provide their own when cloning.
    """
    __tablename__ = 'tbl_prebuilt_agents'

    prebuilt_agent_id = Column(Integer, primary_key=True)
    
    # Agent Metadata
    agent_name = Column(String(255), nullable=False)
    agent_description = Column(Text)
    agent_role = Column(Text)
    agent_instructions = Column(Text)
    
    # Categorization
    category = Column(String(100))  # 'Sales', 'Marketing', 'Support', 'HR'
    tags = Column(ARRAY(Text))  # Searchable tags
    is_featured = Column(Boolean, default=False)
    display_order = Column(Integer, default=0)
    
    # LLM Configuration
    llm_provider = Column(String(50), nullable=False)
    llm_model = Column(String(100), nullable=False)
    temperature = Column(DECIMAL(3, 2), default=0.7)
    max_tokens = Column(Integer, default=1000)
    
    # Features & Settings
    features = Column(JSONB, default={})
    safe_ai_settings = Column(JSONB, default={})
    additional_instructions = Column(Text)
    examples = Column(Text)
    
    # Memory Configuration
    memory_type = Column(String(50))  # 'short_term', 'long_term', NULL
    memory_enabled = Column(Boolean, default=False)
    
    # Tools Configuration (NO credentials)
    required_tools = Column(JSONB, default=[])
    # Example: [
    #   {"tool_name": "hubspot", "action_tools": ["get_contact_by_email"]},
    #   {"tool_name": "gmail", "action_tools": ["send_gmail"]}
    # ]
    
    # Knowledge Base Templates
    knowledge_base_config = Column(JSONB, default={})
    
    # Plan Restrictions
    minimum_plan_level = Column(Integer, default=1)  # 1=Free, 2=Pro, 3=Team, 4=Enterprise
    
    # Status & Visibility
    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=True)
    
    # Statistics
    clone_count = Column(Integer, default=0)
    average_rating = Column(DECIMAL(3, 2))
    
    # Audit
    created_by = Column(Integer)  # Super Admin user_id
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    del_flg = Column(Boolean, default=False)
    
    # Relationships
    cloned_instances = relationship(
        "TenantClonedAgent",
        back_populates="prebuilt_agent",
        cascade="all, delete-orphan"
    )

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "prebuilt_agent_id": self.prebuilt_agent_id,
            "agent_name": self.agent_name,
            "agent_description": self.agent_description,
            "agent_role": self.agent_role,
            "agent_instructions": self.agent_instructions,
            "category": self.category,
            "tags": self.tags or [],
            "is_featured": self.is_featured,
            "display_order": self.display_order,
            "llm": {
                "provider": self.llm_provider,
                "model": self.llm_model,
                "temperature": float(self.temperature) if self.temperature else 0.7,
                "max_tokens": self.max_tokens,
            },
            "features": self.features or {},
            "safe_ai_settings": self.safe_ai_settings or {},
            "additional_instructions": self.additional_instructions,
            "examples": self.examples,
            "memory": {
                "type": self.memory_type,
                "enabled": self.memory_enabled,
            },
            "required_tools": self.required_tools or [],
            "knowledge_base_config": self.knowledge_base_config or {},
            "minimum_plan_level": self.minimum_plan_level,
            "is_active": self.is_active,
            "is_public": self.is_public,
            "clone_count": self.clone_count,
            "average_rating": float(self.average_rating) if self.average_rating else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_required_tool_names(self):
        """Extract list of tool names required by this agent"""
        if not self.required_tools:
            return []
        return [tool.get("tool_name") for tool in self.required_tools if tool.get("tool_name")]


class TenantClonedAgent(db.Model):
    """
    Tracks which prebuilt agents have been cloned to which tenants.
    Links prebuilt templates to actual tenant agent instances.
    """
    __tablename__ = 'tbl_tenant_cloned_agents'

    id = Column(Integer, primary_key=True)
    
    tenant_id = Column(Integer, ForeignKey('tbl_tenants.tenant_id', ondelete='CASCADE'), nullable=False)
    prebuilt_agent_id = Column(Integer, ForeignKey('tbl_prebuilt_agents.prebuilt_agent_id', ondelete='CASCADE'), nullable=False)
    cloned_agent_id = Column(Integer, ForeignKey('tbl_agents.agent_id', ondelete='CASCADE'), nullable=False)
    
    # Track cloning
    cloned_at = Column(TIMESTAMP, default=datetime.utcnow)
    
    # User feedback
    user_rating = Column(Integer)  # 1-5
    user_feedback = Column(Text)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Relationships
    prebuilt_agent = relationship("PrebuiltAgent", back_populates="cloned_instances")
    # tenant = relationship("Tenant")  # Uncomment if Tenant model exists
    # cloned_agent = relationship("Agent")  # Uncomment if needed

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "prebuilt_agent_id": self.prebuilt_agent_id,
            "cloned_agent_id": self.cloned_agent_id,
            "cloned_at": self.cloned_at.isoformat() if self.cloned_at else None,
            "user_rating": self.user_rating,
            "user_feedback": self.user_feedback,
            "is_active": self.is_active,
        }


class PrebuiltAgentAnalytics(db.Model):
    """
    Analytics for prebuilt agents (optional - for Super Admin dashboard)
    """
    __tablename__ = 'tbl_prebuilt_agent_analytics'

    id = Column(Integer, primary_key=True)
    
    prebuilt_agent_id = Column(Integer, ForeignKey('tbl_prebuilt_agents.prebuilt_agent_id', ondelete='CASCADE'), nullable=False)
    
    event_type = Column(String(50), nullable=False)  # 'view', 'clone', 'activate', 'rate'
    tenant_id = Column(Integer, ForeignKey('tbl_tenants.tenant_id', ondelete='SET NULL'))
    
    # metadata = Column(JSONB, default={})
    analytics_metadata = Column("metadata", JSONB, default={})
    
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "prebuilt_agent_id": self.prebuilt_agent_id,
            "event_type": self.event_type,
            "tenant_id": self.tenant_id,
            # "metadata": self.metadata or {},
            "metadata": self.analytics_metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
