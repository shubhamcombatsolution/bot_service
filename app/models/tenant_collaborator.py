from . import db

class Collaborator(db.Model):
    __tablename__ = "tbl_collaborators"

    collaborator_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_tenants.tenant_id", ondelete="CASCADE"),
        nullable=False
    )

    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    phone = db.Column(db.String(20))

    role = db.Column(db.String(50), nullable=False, default="user")
    password_hash = db.Column(db.String(255))

    status = db.Column(db.String(50), default="Active")

    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now(), nullable=False)

    del_flg = db.Column(db.Boolean, default=False)

    # :x: REMOVE THIS:
    # tenant = db.relationship("Tenant", backref="collaborators")