from .. import db

class UPSOriginZoneConfig(db.Model):
    __tablename__ = "tbl_ups_origin_zone_config"

    ups_origin_zone_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    destination_country = db.Column(db.String(100), nullable=False, index=True)

    shipment_direction = db.Column(db.String(20), nullable=False)  # Export / Import
    service_type = db.Column(db.String(50), nullable=False)        # Express, Express Plus, Saver, Expedited

    zone_code = db.Column(db.String(2), nullable=False)            # 01–10

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now()
    )

    del_flg = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint(
            "destination_country",
            "shipment_direction",
            "service_type",
            name="uq_ups_origin_zone"
        ),
    )

    def __repr__(self):
        return (
            f"<UPSOriginZoneConfig {self.destination_country} | "
            f"{self.shipment_direction} | {self.service_type} → Zone {self.zone_code}>"
        )
