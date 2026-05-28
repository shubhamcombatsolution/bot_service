from .. import db
from sqlalchemy import Enum
import enum
import uuid
from ..custombot_access_restriction import CustomBotAccessRestriction




def ValueEnum(enum_cls, name=None):
    return Enum(
        enum_cls,
        values_callable=lambda x: [e.value for e in x],
        name=name or enum_cls.__name__.lower(),
        native_enum=True
    )
# -----------------------------
# ENUMS
# -----------------------------

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
    TRANSPORTATION_AND_LOGISTICS = "Transportation and Logistics"
    INFORMATION_TECHNOLOGY = "Information Technology"
    MEDIA_AND_ENTERTAINMENT = "Media and Entertainment"
    GOVERNMENT = "Government"
    OTHER = "Other"
    REAL_ESTATE = "Real Estate"

class ChannelEnum(enum.Enum):
    WEBSITE = "Website"
    WHATSAPP = "WhatsApp"
    SLACK = "Slack"
    API = "API"


class BotStatusEnum(enum.Enum):
    DRAFT = "Draft"
    CREATED = "Created"
    LIVE = "Live"
    PAUSED = "Paused"


# -----------------------------
# MODEL
# -----------------------------

class CustomBotNew(db.Model):
    __tablename__ = "tbl_custombot_new"

    bot_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    instance_id = db.Column(
        db.String(36),
        unique=True,
        nullable=False,
        default=lambda: str(uuid.uuid4())
    )

    tenant_id = db.Column(db.Integer, db.ForeignKey("tbl_tenants.tenant_id"), nullable=False)

    # STEP 1
    channel = db.Column(ValueEnum(ChannelEnum), nullable=False)
    whatsapp_credentials = db.Column(db.JSON, nullable=True, default=dict)

    # STEP 2 (nullable until filled)
    bot_name = db.Column(db.String(255), nullable=True)
    tone_of_voice = db.Column(Enum(ToneOfVoiceEnum), nullable=True)
    industry = db.Column(Enum(IndustryEnum), nullable=True)
    purpose = db.Column(db.String(1000), nullable=True)
    avatar = db.Column(db.String(255), nullable=True)

    # STEP 3+
    core_features = db.Column(db.JSON, default=dict)
    instructions = db.Column(db.JSON, default=list)
    kb_ids = db.Column(db.JSON, nullable=True, default=list)
    kb_functionalities = db.Column(db.JSON, nullable=True, default=list)


    # Lifecycle
    bot_status = db.Column(
        ValueEnum(BotStatusEnum),
        nullable=False,
        default=BotStatusEnum.DRAFT
    )
    
    
    position = db.Column(db.String(50), nullable=True, default="bottom_right")

    page_config = db.Column(db.String(50), nullable=True, default="all_pages")

    specific_pages = db.Column(db.JSON, nullable=True, default=list)

    theme = db.Column(db.String(100), nullable=True, default="Theme 1")

    colors = db.Column(db.JSON, nullable=True, default=dict)

    background_image = db.Column(db.String(255), nullable=True)
    
    background_color = db.Column(db.String(20), nullable=True)

    disclaimer_text = db.Column(db.String(500), nullable=True)

    greeting_type = db.Column(db.String(50), nullable=True, default="dynamic")

    greeting_message = db.Column(
        db.String(500),
        nullable=True,
        default="Hello! I'm your friendly assistant. How can I help you today?"
    )

    # Conversation memory behavior: 'structured' | 'session' | 'persistent'.
    # NULL is treated as 'session' (load/save scoped to the current session).
    memory_mode = db.Column(db.String(30), nullable=True, default=None)

    published_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_bot_versions.version_id"),
        nullable=True
    )
    last_published_at = db.Column(db.DateTime, nullable=True)
    
    
    access_restriction_type = db.Column(db.SmallInteger, nullable=True, default=None)


    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now()
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.now(),
        onupdate=db.func.now()
    )

    del_flg = db.Column(db.Boolean, default=False)

    diagrams = db.relationship(
        "BotDiagram",
        back_populates="bot",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    
    access_restrictions = db.relationship(
        "CustomBotAccessRestriction",
        back_populates="bot",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    chathistory = db.relationship(
        "ChatHistory",
        back_populates="bot",
        cascade="all, delete-orphan"
    )

    whatsapp_cred = db.relationship(
        "WhatsAppCred",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    slack_cred = db.relationship(
        "SlackCred",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self):
        return f"<CustomBot {self.bot_id} - {self.bot_status}>"
