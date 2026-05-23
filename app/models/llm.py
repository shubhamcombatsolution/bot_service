from . import db


class LLM(db.Model):
    __tablename__ = "tbl_llm"

    llm_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_tenants.tenant_id"),
        nullable=False
    )

    base_llm_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_basellm.base_llm_id"),
        nullable=False
    )

    llm_secret_key = db.Column(db.Text, nullable=False)

    temperature = db.Column(db.Float, default=0.7)

    max_output_tokens = db.Column(db.Integer, default=1024)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now()
    )

    del_flg = db.Column(db.Boolean, default=False)
    api_key_temp = db.Column(db.String(255), nullable=False)

    provider_id = db.Column(db.Integer, db.ForeignKey('tbl_basellm.base_llm_id'), nullable=False)
    model_name_id = db.Column(db.Integer, db.ForeignKey('tbl_basellm.base_llm_id'), nullable=False)
    model_type_id = db.Column(db.Integer, db.ForeignKey('tbl_basellm.base_llm_id'), nullable=False)
    tenant = db.relationship("Tenant", backref="llms")
    
    provider = db.relationship(
        'BaseLLM',
        foreign_keys=[provider_id],
        backref='provider_llms'
    )

    model_name = db.relationship(
        'BaseLLM',
        foreign_keys=[model_name_id],
        backref='model_name_llms'
    )

    model_type = db.relationship(
        'BaseLLM',
        foreign_keys=[model_type_id],
        backref='model_type_llms'
    )

    # 🔥 FIX THIS (VERY IMPORTANT)
    base_llm = db.relationship(
        "BaseLLM",
        foreign_keys=[base_llm_id]
    )

    def __repr__(self):
        return f"<LLM {self.base_llm.base_model_name} ({self.base_llm.base_provider}) Tenant {self.tenant_id}>"
