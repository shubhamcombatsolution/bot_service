from . import db
from sqlalchemy.orm import relationship
from sqlalchemy import Enum
import enum
import uuid
from .custombot_access_restriction import CustomBotAccessRestriction
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import Integer

# Enum for Tone of Voice
class ToneOfVoiceEnum(enum.Enum):
    FRIENDLY = "Friendly"
    PROFESSIONAL = "Professional"
    CASUAL = "Casual"
    FORMAL = "Formal"
    HUMOROUS = "Humorous"
    EMPATHETIC = "Empathetic"
    SUPPORTIVE = "Supportive"
    NEUTRAL = "Neutral"
    CONFIDENT = "Confident"
    AUTHORITATIVE = "Authoritative"
    PLAYFUL = "Playful"
    ENTHUSIASTIC = "Enthusiastic"
    REASSURING = "Reassuring"
    POLITE = "Polite"
    DIRECT = "Direct"
     

# Enum for Industry
class IndustryEnum(enum.Enum):
    AGRICULTURE_AND_FARMING = "Agriculture and Farming"
    FORESTRY = "Forestry"
    FISHING_AND_FISHERIES = "Fishing and Fisheries"
    MINING_AND_QUARRYING = "Mining and Quarrying"
    AUTOMOTIVE_MANUFACTURING = "Automotive Manufacturing"
    ELECTRONICS_AND_ELECTRICAL = "Electronics and Electrical"
    TEXTILES_AND_APPAREL = "Textiles and Apparel"
    CHEMICALS_AND_PETROCHEMICALS = "Chemicals and Petrochemicals"
    FOOD_AND_BEVERAGE = "Food and Beverage"
    RETAIL = "Retail"
    HEALTHCARE = "Healthcare"
    EDUCATION = "Education"
    BANKING_AND_FINANCIAL = "Banking and Financial"
    HOSPITALITY_AND_TOURISM = "Hospitality and Tourism"
    TRANSPORTATION_AND_LOGISTICS = "Transportaion and Logistics"
    INFORMATION_TECHNOLOGY = "Information Technology"
    MEDIA_AND_ENTERTAINMNET = "Media and Entertainment"
    GOVERNMENT = "Government"
    OTHER = "Other"
    REAL_ESTATE = "Real Estate"

class CustomBot(db.Model):
    __tablename__ = 'tbl_custombot'
    
    bot_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    instance_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))  # New UUID field
    tenant_id = db.Column(db.Integer, db.ForeignKey('tbl_tenants.tenant_id'))
    tenant = db.relationship('Tenant', back_populates="custom_bots", overlaps="associated_tenant")
    
    bot_name = db.Column(db.String(255), nullable=False)
    
    # Dropdown fields for tone_of_voice and industry
    tone_of_voice = db.Column(Enum(ToneOfVoiceEnum), nullable=False)
    industry = db.Column(Enum(IndustryEnum), nullable=False)
    
    avatar = db.Column(db.String(255), nullable=False)
    # avatar = db.Column(db.LargeBinary, nullable=True)
    purpose = db.Column(db.String(1000), nullable=False)
    
    core_features = db.Column(db.JSON, default=[]) 
    instructions = db.Column(db.JSON, default=[])
    
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, default=db.func.now(), onupdate=db.func.now())
    del_flg = db.Column(db.Boolean, default=False)
    status = db.Column(db.Boolean, default=True)
    bot_status = db.Column(db.String, default="InProgerss")
    bot_type = db.Column(db.String(255), default = '')
  
    # knowledge_base_id = db.Column(db.Integer, db.ForeignKey('tbl_knowledge_base.knowledge_base_id'), nullable=True)
    # knowledge_base = db.relationship('KnowledgeBase', backref='bot')
    # knowledge_base_id = db.Column(
    #     db.Integer,
    #     db.ForeignKey('tbl_knowledge_base.knowledge_base_id'),
    #     nullable=True
    # )

    kb_ids = db.Column(db.JSON, nullable=True, default=[])

    kb_functionalities = db.Column(db.JSON, nullable=True)

    
    theme = db.Column(db.String(100), nullable=True, default="Theme 1")
    disclaimer_text = db.Column(db.String(500), nullable=True)
    background_image = db.Column(db.String(255), nullable=True)
    colors = db.Column(db.JSON, default={})  # Store color sets as JSON
    greeting_type = db.Column(db.String(100), nullable=True)
    greeting_message = db.Column(db.String(500), nullable=True, default="Hello! I'm your friendly assistant. How can I help you today?")  # New field
    access_restriction_type = db.Column(db.SmallInteger, nullable=True, default=None)
    # diagrams = db.relationship('BotDiagram', back_populates="bot", cascade="all, delete-orphan")
    # chathistory = db.relationship('ChatHistory', back_populates="bot", cascade="all, delete-orphan")
    lead = db.relationship('Lead', back_populates="bot", cascade="all, delete-orphan")
    # access_restrictions = db.relationship(
    #     "CustomBotAccessRestriction",
    #     back_populates="bot",
    #     cascade="all, delete-orphan",
    #     lazy="selectin"  
    # )
    def __repr__(self):
        return f"<CustomBot {self.bot_name}>"
