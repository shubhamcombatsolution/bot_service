from .. import db

class UPSFreightCharge(db.Model):
    __tablename__ = "tbl_ups_freight_charges"

    ups_freight_charge_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    service_type = db.Column(db.String(50), nullable=False)
    shipment_direction = db.Column(db.String(20), nullable=False)
    package_type = db.Column(db.String(20), nullable=False)
    weight_slab = db.Column(db.String(20), nullable=False)

    zone_01 = db.Column(db.Numeric(12, 2), nullable=True)
    zone_02 = db.Column(db.Numeric(12, 2), nullable=True)
    zone_03 = db.Column(db.Numeric(12, 2), nullable=True)
    zone_04 = db.Column(db.Numeric(12, 2), nullable=True)
    zone_05 = db.Column(db.Numeric(12, 2), nullable=True)
    zone_06 = db.Column(db.Numeric(12, 2), nullable=True)
    zone_07 = db.Column(db.Numeric(12, 2), nullable=True)
    zone_08 = db.Column(db.Numeric(12, 2), nullable=True)
    zone_09 = db.Column(db.Numeric(12, 2), nullable=True)
    zone_10 = db.Column(db.Numeric(12, 2), nullable=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now()
    )

    del_flg = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return (
            f"<UPSFreightCharge {self.service_type} | "
            f"{self.shipment_direction} | {self.package_type} | {self.weight_slab}>"
        )
