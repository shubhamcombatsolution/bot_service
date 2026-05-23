from .. import db

class FedexOriginZoneConfig(db.Model):
    __tablename__ = "tbl_fedex_origin_zone_config"

    fedex_origin_zone_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    origin_country = db.Column(db.String(100), nullable=False, unique=True, index=True)

    # Zone mapping
    zone_code = db.Column(db.String(2), nullable=False)  # A, B, C, ... L

    # Service availability
    ip = db.Column(db.Boolean, default=False)
    ipf = db.Column(db.Boolean, default=False)
    ie = db.Column(db.Boolean, default=False)
    ief = db.Column(db.Boolean, default=False)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now()
    )

    del_flg = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<FedexOriginZoneConfig {self.origin_country} → Zone {self.zone_code}>"
