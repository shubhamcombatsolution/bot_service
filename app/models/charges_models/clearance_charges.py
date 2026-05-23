from .. import db

class ClearanceCharges(db.Model):
    __tablename__ = 'tbl_clearance_charges'

    clearance_charge_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    carrier = db.Column(db.String(50), nullable=False)
    shipment_type = db.Column(db.String(50), nullable=False)
    charge_name = db.Column(db.String(150), nullable=False)

    amount_min = db.Column(db.Numeric(10, 2), nullable=True)
    per_kg_rate = db.Column(db.Numeric(10, 2), nullable=True)
    duty_percent = db.Column(db.Numeric(5, 2), nullable=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now()
    )

    # Soft delete flag
    del_flg = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return (
            f"<ClearanceCharges {self.carrier} | "
            f"{self.shipment_type} | {self.charge_name}>"
        )
