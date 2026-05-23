from . import db

class SystemLLM(db.Model):
    __tablename__ = 'tbl_system_llm'

    llm_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    provider = db.Column(db.String(255), nullable=False)
    model_name = db.Column(db.String(255), nullable=False)
    api_key_temp = db.Column(db.String(255), nullable=False)
    max_output_tokens = db.Column(db.Integer, default=1024)
    
    # Ensure 'created_at' column has a default value of the current timestamp
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    # 'del_flg' marks soft deletion (default value 0 means not deleted)
    del_flg = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<LLM {self.model_name} by {self.provider}>"
