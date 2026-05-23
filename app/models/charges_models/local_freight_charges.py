from .. import db

class LocalFreightCharge(db.Model):
    __tablename__ = 'tbl_local_freight_charges'

    local_freight_charge_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    carrier = db.Column(db.String(50), nullable=False)
    service_type = db.Column(db.String(50), nullable=False)

    route_type = db.Column(db.String(100), nullable=False)
    weight_slab = db.Column(db.String(100), nullable=False)

    rate = db.Column(db.Numeric(12, 4), nullable=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now()
    )

    del_flg = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return (
            f"<LocalFreightCharge {self.carrier} | "
            f"{self.service_type} | {self.route_type} | {self.weight_slab}>"
        )
