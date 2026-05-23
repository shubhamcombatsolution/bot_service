from flask import Blueprint, request, jsonify
from app.models import ContactUs
from app.database.DatabaseOperationPostgreSQL import db_session

# Define Blueprint
contact_us_blueprint = Blueprint("contact_us", __name__)

# Create a new Contact Us entry
@contact_us_blueprint.route("/submit", methods=["POST"])
def create_contact_us_entry():
    try:
        data = request.json
        required_fields = ["name", "work_mail", "query"]

        # Check if all required fields are provided
        if not all(field in data for field in required_fields):
            return jsonify({
                "data": {},
                "message": "Missing required fields",
                "status": "error"
            }), 400

        # Start a session for database operation
        session = next(db_session())
        try:
            # Create a new ContactUs entry
            new_contact_us = ContactUs(
                name=data["name"],
                work_mail=data["work_mail"],
                query=data["query"]
            )
            session.add(new_contact_us)
            session.commit()

            return jsonify({
                "data": {"contactus_id": new_contact_us.contactus_id},
                "message": "Contact Us entry created successfully",
                "status": "success"
            }), 201
        except Exception as e:
            session.rollback()
            return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
        finally:
            session.close()
    except Exception as e:
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
