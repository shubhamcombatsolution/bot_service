from . import db

class SystemEmbeddingModel(db.Model):
    __tablename__ = 'tbl_system_embedding_models'

    embedding_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    model_name = db.Column(db.String(255), nullable=False)
    api_key = db.Column(db.String(255), nullable=False)
    chunk_size = db.Column(db.Integer, default=None)
    chunk_overlap = db.Column(db.Integer, default=None)
    
    # Ensure 'created_at' column has a default value of the current timestamp
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    # 'del_flg' marks soft deletion (default value 0 means not deleted)
    del_flg = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<EmbeddingModel {self.model_name}>"
