from .. import db

class OtherCharge(db.Model):
    __tablename__ = "tbl_other_charges"

    other_charge_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    carrier = db.Column(db.String(50), nullable=False)
    charge_category = db.Column(db.String(50), nullable=False)
    charge_name = db.Column(db.String(150), nullable=False)

    applies_to = db.Column(db.String(50), nullable=False)

    condition_key = db.Column(db.String(50), nullable=True)
    condition_value = db.Column(db.String(100), nullable=True)

    amount = db.Column(db.Numeric(12, 4), nullable=True)
    amount_type = db.Column(db.String(20), nullable=False)  
    # fixed | percentage | per_kg

    currency = db.Column(db.String(10), nullable=False)
    remarks = db.Column(db.Text, nullable=True)
    reference_link = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now()
    )

    del_flg = db.Column(db.Boolean, default=False)
