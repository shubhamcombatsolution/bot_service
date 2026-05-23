from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, Boolean, Float, Enum, ForeignKey, DECIMAL
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import enum

Base = declarative_base()

# Models
class LoginUser(Base):
    __tablename__ = 'tbl_loginuser'

    login_id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=False)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    tenant_id = Column(Integer, nullable=True)
    role = Column(String(100), nullable=True)
    del_flg = Column(Boolean, default=False)

class Role(Base):
    __tablename__ = 'tbl_roles'

    role_id = Column(Integer, primary_key=True, autoincrement=True)
    role_name = Column(String(100), nullable=False, unique=True)
    role_description = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    del_flg = Column(Boolean, default=False)

class Tenant(Base):
    __tablename__ = 'tbl_tenants'

    tenant_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_name = Column(String(255), nullable=False)
    tenant_key = Column(String(255), nullable=False)
    tenant_address = Column(String(255), nullable=False)
    tenant_emailid = Column(String(255), nullable=False, unique=True)
    tenant_contact = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    tenant_emailid_verify = Column(Boolean, default=False)
    tenant_GSTNNo = Column(String(100), nullable=True)
    tenant_PAN = Column(String(100), nullable=True)
    del_flg = Column(Boolean, default=False)
    tenant_city = Column(String(100), nullable=True)
    tenant_country = Column(String(100), nullable=True)
    tenant_postcode = Column(String(100), nullable=True)

# Database Connection and Session
DATABASE_URL = "sqlite:///example.db"  # Replace with your database connection string
engine = create_engine(DATABASE_URL, echo=True)
Session = sessionmaker(bind=engine)
session = Session()

# Insert Function
def insert_record(model, **kwargs):
    try:
        record = model(**kwargs)
        session.add(record)
        session.commit()
        return record
    except Exception as e:
        session.rollback()
        raise e

# Update Function
def update_record(model, record_id, **kwargs):
    try:
        record = session.query(model).filter_by(id=record_id).first()
        if not record:
            raise ValueError("Record not found")

        for key, value in kwargs.items():
            setattr(record, key, value)

        session.commit()
        return record
    except Exception as e:
        session.rollback()
        raise e

# Example Usage
if __name__ == "__main__":
    # Create tables
    Base.metadata.create_all(engine)

    # Insert Example
    new_user = insert_record(LoginUser, username="JohnDoe", password_hash="hashed_pwd", email="john@example.com")
    print(f"Inserted User: {new_user}")

    # Update Example
    updated_user = update_record(LoginUser, new_user.login_id, username="JaneDoe")
    print(f"Updated User: {updated_user}")
