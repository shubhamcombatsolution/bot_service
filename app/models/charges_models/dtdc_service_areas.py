from .. import db

class DTDCServiceArea(db.Model):
    __tablename__ = 'tbl_dtdc_service_areas'

    dtdc_service_area_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    category = db.Column(
        db.String(50),
        nullable=False
    )
    # e.g. 'metro', 'special_destination'

    location_name = db.Column(
        db.String(100),
        nullable=False
    )
    # city or state name

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now()
    )

    del_flg = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<DTDCServiceArea {self.category} | {self.location_name}>"
