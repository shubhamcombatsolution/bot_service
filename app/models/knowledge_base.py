from . import db

class KnowledgeBase(db.Model):
    __tablename__ = 'tbl_knowledge_base'

    # Primary Key
    knowledge_base_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Foreign Key
    tenant_id = db.Column(db.Integer, db.ForeignKey('tbl_tenants.tenant_id'), nullable=False)

    # Core KB fields
    knowledge_base_name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    upload_pdf = db.Column(db.Text, nullable=True)
    upload_media = db.Column(db.Text, nullable=True)
    scrap_url = db.Column(db.Text, nullable=True)

    max_crawl_pages = db.Column(db.Integer, nullable=True)
    max_crawl_depth = db.Column(db.Integer, nullable=True)
    dynamic_wait = db.Column(db.Integer, nullable=True)

    raw_text = db.Column(db.Text)

    chunk_size = db.Column(db.Integer, nullable=True)
    chunk_overlap = db.Column(db.Integer, nullable=True)

    collection_name = db.Column(db.String(255), nullable=True)
    media_collection_name = db.Column(db.String(255), nullable=True)
    media_type = db.Column(db.String(50), nullable=True)

    kb_summary = db.Column(db.Text, nullable=True)

    # 🔥 ASYNC PROCESSING FIELDS (NEW)
    status = db.Column(
        db.String(20),
        nullable=False,
        default="PENDING",
        index=True
    )
    build_task_id = db.Column(db.String(255), nullable=True, unique=True)

    total_chunks = db.Column(db.Integer, nullable=True)
    processed_chunks = db.Column(db.Integer, nullable=True, default=0)

    error_message = db.Column(db.Text, nullable=True)

    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, default=db.func.now(), onupdate=db.func.now())

    # Soft delete
    del_flg = db.Column(db.Boolean, default=False)

    # Relationship
    tenant = db.relationship('Tenant', backref='knowledge_bases')

    def __repr__(self):
        return f"<KnowledgeBase {self.knowledge_base_name} | status={self.status}>"


