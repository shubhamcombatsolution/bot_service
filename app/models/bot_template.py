"""
bot_template.py

SQLAlchemy model for tbl_bot_templates.
Super Admin converts an existing bot (from tenant 0001) into a reusable
template that all tenants can browse and use as a starting point.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.models import db


class BotTemplate(db.Model):
    """
    Stores bot templates created by the Super Admin.
    All fields from the source bot are snapshot-copied here so the template
    remains independent of the original bot record.
    """
    __tablename__ = 'tbl_bot_templates'

    # ── Primary key ────────────────────────────────────────────────────────
    template_id = Column(Integer, primary_key=True, autoincrement=True)

    # ── Template meta ──────────────────────────────────────────────────────
    template_name        = Column(String(255), nullable=False)
    template_description = Column(Text, nullable=True)

    # ── Source reference ────────────────────────────────────────────────────
    # Which bot was this template created from?
    source_bot_id   = Column(Integer, nullable=True)   # original bot_id
    source_bot_name = Column(String(255), nullable=True)

    # ── Snapshot of bot data ────────────────────────────────────────────────
    # Core identity
    bot_name     = Column(String(255), nullable=True)
    avatar       = Column(String(255), nullable=True)
    purpose      = Column(Text, nullable=True)
    bot_type     = Column(String(255), nullable=True)
    channel      = Column(String(255), nullable=True)

    # Personality
    tone_of_voice = Column(String(100), nullable=True)
    industry      = Column(String(100), nullable=True)

    # Content
    core_features      = Column(JSONB, nullable=True, default=list)
    instructions       = Column(JSONB, nullable=True, default=list)
    kb_ids             = Column(JSONB, nullable=True, default=list)
    kb_functionalities = Column(JSONB, nullable=True)

    # UI / theme
    theme            = Column(String(100), nullable=True)
    disclaimer_text  = Column(String(500), nullable=True)
    background_image = Column(String(255), nullable=True)
    colors           = Column(JSONB, nullable=True, default=dict)
    greeting_type    = Column(String(100), nullable=True)
    greeting_message = Column(String(500), nullable=True)

    # Workflow / diagram snapshot (full JSON)
    workflow_data = Column(JSONB, nullable=True)

    # ── Status ─────────────────────────────────────────────────────────────
    is_active  = Column(Boolean, default=True, nullable=False)
    del_flg    = Column(Boolean, default=False, nullable=False)

    # ── Timestamps ─────────────────────────────────────────────────────────
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    # ───────────────────────────────────────────────────────────────────────
    def to_dict(self):
        return {
            "template_id":          self.template_id,
            "template_name":        self.template_name,
            "template_description": self.template_description,
            "source_bot_id":        self.source_bot_id,
            "source_bot_name":      self.source_bot_name,
            # bot snapshot
            "bot_name":             self.bot_name,
            "avatar":               self.avatar,
            "purpose":              self.purpose,
            "bot_type":             self.bot_type,
            "channel":              self.channel,
            "tone_of_voice":        self.tone_of_voice,
            "industry":             self.industry,
            "core_features":        self.core_features or [],
            "instructions":         self.instructions or [],
            "kb_ids":               self.kb_ids or [],
            "kb_functionalities":   self.kb_functionalities,
            # tool_names stored in kb_functionalities (list of strings)
            "tool_names":           self.kb_functionalities if isinstance(self.kb_functionalities, list) else [],
            "theme":                self.theme,
            "disclaimer_text":      self.disclaimer_text,
            "background_image":     self.background_image,
            "colors":               self.colors or {},
            "greeting_type":        self.greeting_type,
            "greeting_message":     self.greeting_message,
            "workflow_data":        self.workflow_data,
            # status
            "is_active":            self.is_active,
            "status":               "Active" if self.is_active else "Inactive",
            # timestamps
            "created_at":           self.created_at.isoformat() if self.created_at else None,
            "updated_at":           self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<BotTemplate id={self.template_id} name={self.template_name!r}>"
