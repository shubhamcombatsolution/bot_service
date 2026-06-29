# app/models/agent.py

import enum
from . import db
from sqlalchemy.ext.mutable import MutableList, MutableDict
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Enum

def ValueEnum(enum_cls, name=None):
    return Enum(
        enum_cls,
        values_callable=lambda x: [e.value for e in x],
        name=name or enum_cls.__name__.lower(),
        native_enum=True
    )

# ---------------------------------------------------
# Agent Status Enum
# ---------------------------------------------------
class AgentStatusEnum(enum.Enum):
    DRAFT = "Draft"
    CREATED = "Created"
    LIVE = "Live"
    PAUSED = "Paused"
    DELETED = "Deleted"

class Agent(db.Model):
    __tablename__ = "tbl_agents"

    # ---------------------------------------------------
    # Primary
    # ---------------------------------------------------
    agent_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_tenants.tenant_id"),
        nullable=False,
        index=True
    )

    agent_status = db.Column(
        ValueEnum(AgentStatusEnum, name="agentstatusenum"),
        nullable=False,
        default=AgentStatusEnum.DRAFT.value,
        index=True
    )

    del_flg = db.Column(db.Boolean, default=False, nullable=False)

    # ---------------------------------------------------
    # STEP 1 — Overview
    # ---------------------------------------------------
    agent_name = db.Column(db.String(150), nullable=True)
    agent_description = db.Column(db.Text, nullable=True)
    agent_type = db.Column(db.String(50), nullable=True)
    persona_style = db.Column(db.String(50), nullable=True)
    llm_provider_id = db.Column(db.Integer, db.ForeignKey('tbl_llm.llm_id'), nullable=False)
    tool_id = db.Column(db.Integer, db.ForeignKey('tbl_tools.tool_id'), nullable=False)
    memory_plugin = db.Column(db.String(20), default=None)
    # ---------------------------------------------------
    # STEP 2 — Behaviour
    # ---------------------------------------------------
    agent_instructions = db.Column(db.Text, nullable=True)
    instruction_mode = db.Column(db.String(50), nullable=True)

    # ---------------------------------------------------
    # STEP 3 — Knowledge Base
    # ---------------------------------------------------
    knowledge_base_ids = db.Column(
        MutableList.as_mutable(JSONB),
        default=list,
        nullable=False
    )

    # ---------------------------------------------------
    # STEP 4 — Guardrails
    # ---------------------------------------------------
    guardrails = db.Column(
        MutableDict.as_mutable(JSONB),
        default=dict,
        nullable=False
    )

    # ---------------------------------------------------
    # STEP 5 — AI Config
    # ---------------------------------------------------
 
    llm_model_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_llm.llm_id"),
        nullable=True
    )

    temperature = db.Column(db.Float, nullable=True)
    max_tokens = db.Column(db.Integer, nullable=True)
    memory_mode = db.Column(db.String(30), nullable=True)

    # ---------------------------------------------------
    # STEP 6 — Conversation
    # ---------------------------------------------------
    greeting_message = db.Column(db.Text, nullable=True)
    language = db.Column(db.String(20), nullable=True)
    timezone = db.Column(db.String(50), nullable=True)
    tone = db.Column(db.String(30), nullable=True)
    emoji_mode = db.Column(db.String(30), nullable=True)
    availability_mode = db.Column(db.String(30), nullable=True)
    tool_type = db.Column(db.String, nullable=False)
    # ---------------------------------------------------
    # System
    # ---------------------------------------------------

    # Tracks the highest wizard step saved (0=overview,1=behaviour,2=kb,3=guardrails,4=aiconfig,5=published)
    completed_step = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    import_source = db.Column(db.String(20), nullable=True, default=None)
    imported_at   = db.Column(db.DateTime, nullable=True, default=None)
    additional_instructions = db.Column(db.Text, nullable=True)
    agent_key = db.Column(db.String(120), unique=True, nullable=True)
    deployment_method = db.Column(db.String(30), nullable=True)
    tool = db.relationship('Tools', backref=db.backref('agents', lazy=True))
    agent_role = db.Column(db.Text, nullable=False)
    # ---------------------------------------------------
    # Relationships
    # ---------------------------------------------------
    tenant = db.relationship(
        "Tenant",
        back_populates="agents"
    )


    llm_model = db.relationship(
        "LLM",
        foreign_keys=[llm_model_id]
    )

    conversations = db.relationship(
        "Conversation",
        back_populates="agent",
        cascade="all, delete-orphan"
    )
    Examples = db.Column(db.Text)
    
    published_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_agent_versions.version_id"),
        nullable=True
    )

    last_deployed_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )
    # Feature toggles
    features = db.Column(
        MutableDict.as_mutable(JSONB),
        default=dict,
        nullable=False
    )

    # Safe AI settings
    safe_ai_settings = db.Column(
        MutableDict.as_mutable(JSONB),
        default=dict,
        nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False
    )
    def __repr__(self):
        provider_name = None
        model_name = None
        if self.llm_model:
            provider_rel = getattr(self.llm_model, "provider", None)
            model_name_rel = getattr(self.llm_model, "model_name", None)
            base_llm_rel = getattr(self.llm_model, "base_llm", None)
            provider_name = (
                getattr(provider_rel, "base_provider", None)
                or getattr(base_llm_rel, "base_provider", None)
            )
            model_name = (
                getattr(model_name_rel, "base_model_name", None)
                or getattr(base_llm_rel, "base_model_name", None)
            )

        return (
            f"<Agent {self.agent_name} using {provider_name} - {model_name} "
            f"for Tenant {self.tenant_id}>"
        )

    # ✅ MUST BE INSIDE CLASS
    def to_dict(self):
        agent_status = (
            self.agent_status.value
            if hasattr(self.agent_status, "value")
            else self.agent_status
        )
        tool_name = getattr(self.tool, "tool_name", None)
        tool_description = getattr(self.tool, "tool_description", None)
        llm_model_name = None
        llm_provider_name = None
        if self.llm_model and getattr(self.llm_model, "base_llm", None):
            llm_model_name = getattr(self.llm_model.base_llm, "base_model_name", None)
            llm_provider_name = getattr(self.llm_model.base_llm, "base_provider", None)

        return {
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "agent_status": agent_status,

            "agent_name": self.agent_name,
            "agent_description": self.agent_description,
            "agent_type": self.agent_type,
            "persona_style": self.persona_style,

            "llm_provider_id": self.llm_provider_id,
            "llm_model_id": self.llm_model_id,
            "llm_provider_name": llm_provider_name,
            "llm_model_name": llm_model_name,

            "agent_role": self.agent_role,
            "agent_instructions": self.agent_instructions,
            "instruction_mode": self.instruction_mode,
            "additional_instructions": self.additional_instructions,

            "tool_id": self.tool_id,
            "tool_type": self.tool_type,
            "tool_name": tool_name,
            "tool_description": tool_description,

            "knowledge_base_ids": self.knowledge_base_ids,
            "knowledge_base_count": len(self.knowledge_base_ids or []),

            "Examples": self.Examples,
            "greeting_message": self.greeting_message,
            "language": self.language,
            "timezone": self.timezone,
            "tone": self.tone,
            "emoji_mode": self.emoji_mode,
            "availability_mode": self.availability_mode,

            # ✅ These will now appear in API
            "features": self.features or {},
            "safe_ai_settings": self.safe_ai_settings or {},

            "memory_plugin": self.memory_plugin,
            "memory_mode": self.memory_mode,
            "deployment_method": self.deployment_method,
            "agent_key": self.agent_key,
            "published_version_id": self.published_version_id,
            "last_deployed_at": self.last_deployed_at.isoformat() if self.last_deployed_at else None,

            "import_source": self.import_source,
            "imported_at":   self.imported_at.isoformat() if self.imported_at else None,

            "created_at":    self.created_at.isoformat() if self.created_at else None,
            "updated_at":    self.updated_at.isoformat() if self.updated_at else None,

            "del_flg": self.del_flg,
            "completed_step": self.completed_step or 0
        }
