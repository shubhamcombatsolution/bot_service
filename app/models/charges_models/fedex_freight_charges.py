from .. import db

class FedexFreightCharge(db.Model):
    __tablename__ = "tbl_fedex_freight_charges"

    fedex_freight_charge_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    package_type = db.Column(db.String(50), nullable=False)
    weight_kg = db.Column(db.Numeric(10, 2), nullable=False)

    zone_a = db.Column(db.Numeric(12, 2), nullable=True)
    zone_b = db.Column(db.Numeric(12, 2), nullable=True)
    zone_e = db.Column(db.Numeric(12, 2), nullable=True)
    zone_f = db.Column(db.Numeric(12, 2), nullable=True)
    zone_g = db.Column(db.Numeric(12, 2), nullable=True)
    zone_h = db.Column(db.Numeric(12, 2), nullable=True)
    zone_i = db.Column(db.Numeric(12, 2), nullable=True)
    zone_j = db.Column(db.Numeric(12, 2), nullable=True)
    zone_k = db.Column(db.Numeric(12, 2), nullable=True)
    zone_l = db.Column(db.Numeric(12, 2), nullable=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now()
    )

    del_flg = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<FedexFreightCharge {self.package_type} {self.weight_kg}kg>"
