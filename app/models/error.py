from . import db

class Error(db.Model):
    __tablename__ = 'tbl_error'
    error_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    error_message = db.Column(db.Text, nullable=False)
    error_code = db.Column(db.String(50), default=None)
     # Ensure 'created_at' column has a default value of the current timestamp
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
     
    tenant_id = db.Column(db.Integer, db.ForeignKey('tbl_tenants.tenant_id'), default=None)
    bot_id = db.Column(db.Integer, default=None)
    del_flg = db.Column(db.Boolean, default=False)