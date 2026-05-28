from . import db
from sqlalchemy import func

class Conversation(db.Model):
    __tablename__ = 'tbl_conversations'

    conversation_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Foreign Key to tbl_tenants
    tenant_id = db.Column(db.Integer, db.ForeignKey('tbl_tenants.tenant_id'), nullable=False)

    # Foreign Key to tbl_agents
    agent_id = db.Column(db.Integer, db.ForeignKey('tbl_agents.agent_id'), nullable=False)

    # Groups turns belonging to the same chat session (used by "short_term"/Session mode).
    session_id = db.Column(db.String(64), nullable=True, index=True)

    # Scopes persistent memory to a specific sender/thread from a trigger channel.
    # Format: "wa:<phone>", "slack:<user_id>:<channel_id>", "gmail:<email>"
    # NULL means no trigger context — shared agent memory (pre-existing behaviour).
    conversation_key = db.Column(db.String(255), nullable=True, index=True)

    user_input = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    memory_type = db.Column(db.String(20), nullable=False)

    # Timestamp column
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())

    # Relationships
    tenant = db.relationship(
        'Tenant',
        back_populates="conversations"
    )

    agent = db.relationship(
        'Agent',
        back_populates="conversations"
    )

    def __repr__(self):
        return f"<Conversation id={self.conversation_id} agent_id={self.agent_id} tenant_id={self.tenant_id} memory_type={self.memory_type} session_id={self.session_id}>"