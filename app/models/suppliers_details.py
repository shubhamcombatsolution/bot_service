from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class SupplierDetails(db.Model):
    __tablename__ = 'tbl_suppliers_details'

    supplier_id = db.Column('supplier_id', db.Integer, primary_key=True)
    company_name = db.Column('Company name', db.String(255))
    company_owner = db.Column('Company owner', db.String(255))
    supplier_name = db.Column('Supplier Name', db.String(255))
    phone_number = db.Column('Phone Number', db.String(50))
    supplier_email = db.Column('Supplier Email', db.String(255))
    city = db.Column('City', db.String(100))
    country_region = db.Column('Country/Region', db.String(100))
    pincode = db.Column('Pincode', db.String(20))
    address = db.Column('Address', db.String(255))

    def __repr__(self):
        return f"<SupplierDetails {self.supplier_id} - {self.company_name} - {self.supplier_name}>"
