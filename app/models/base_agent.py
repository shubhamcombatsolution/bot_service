from . import db

class BaseAgent(db.Model):
    __tablename__ = 'tbl_base_agents'

    agent_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    agent_name = db.Column(db.String(100), nullable=False)
    agent_description = db.Column(db.Text, nullable=False)

    agent_role = db.Column(db.Text, nullable=False)
    agent_instructions = db.Column(db.Text)

    Examples = db.Column(db.Text)

    # Timestamp columns
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())

    del_flg = db.Column(db.Boolean, default=False, nullable=False)
    
    def __repr__(self):
        return f"<BaseAgent {self.agent_name}>"
        