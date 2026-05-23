from sqlalchemy.exc import IntegrityError
from models import db

def insert_record(model, **kwargs):
    try:
        record = model(**kwargs)
        db.session.add(record)
        db.session.commit()
        return {"message": "Record added successfully", "record": record.id}
    except IntegrityError as e:
        db.session.rollback()
        return {"error": str(e.orig)}

def update_record(model, **filters):
    try:
        record = model.query.filter_by(**filters).first()
        if not record:
            return {"error": "Record not found"}
        for key, value in filters.items():
            if key in model.__table__.columns:
                setattr(record, key, value)
        db.session.commit()
        return {"message": "Record updated successfully"}
    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}

def get_all_records(model):
    return [record.as_dict() for record in model.query.all()]

def delete_record(model, **filters):
    try:
        record = model.query.filter_by(**filters).first()
        if not record:
            return {"error": "Record not found"}
        db.session.delete(record)
        db.session.commit()
        return {"message": "Record deleted successfully"}
    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}

# Utility function to convert SQLAlchemy object to dictionary
def as_dict(self):
    return {column.name: getattr(self, column.name) for column in self.__table__.columns}
