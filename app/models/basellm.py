from . import db

class BaseLLM(db.Model):
    __tablename__ = 'tbl_basellm'

    base_llm_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    base_provider = db.Column(db.String(255), nullable=False)
    base_model_name = db.Column(db.String(255), nullable=False)
    base_model_type = db.Column(db.String(100), nullable = False)

    # Ensure 'created_at' column has a default value of the current timestamp
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    # 'del_flg' marks soft deletion (default value 0 means not deleted)
    del_flg = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<LLM {self.base_model_name} by {self.base_provider}>"

