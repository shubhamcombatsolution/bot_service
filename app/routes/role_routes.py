from flask import Blueprint, request, jsonify
from datetime import datetime
from app.models.role import Role
from app.database.DatabaseOperationPostgreSQL import db_session
from flask_jwt_extended import create_access_token, jwt_required, unset_jwt_cookies
role_blueprint = Blueprint("role", __name__)

# Role Registration or Update
@role_blueprint.route("/register", methods=["POST"])
@jwt_required()
def role_registration():
    try:
        print(f"role   test")
        data = request.json
        required_fields = ["role_name", "role_description"]
        print(f"role   01")
        # Check if all required fields are present
        if not all(field in data for field in required_fields):
            return jsonify({
                "data": {},
                "message": "Missing required fields",
                "status": "error"
            }), 400

        # Get the session
        session = next(db_session())  

        try:
            print(f"role   test")
            # Check if role already exists
            existing_role = session.query(Role).filter_by(role_name=data["role_name"]).first()
            print(f"role   {existing_role}")
            if existing_role:
                # Update existing role details
                existing_role.role_description = data["role_description"]
                # Commit the changes
                session.commit()

                return jsonify({
                    "data": {
                        "role_id": existing_role.role_id
                    },
                    "message": "Role information updated successfully",
                    "status": "success"
                }), 200
            else:
                # Create new role if it doesn't exist
                new_role = Role(
                    role_name=data["role_name"],
                    role_description=data["role_description"]
                )
              
                session.add(new_role)

                # Commit the changes
                session.commit()

                # Get the role ID of the newly created role
                role_id = new_role.role_id

                return jsonify({
                    "data": {
                        "role_id": role_id
                    },
                    "message": "Role registered successfully",
                    "status": "success"
                }), 201
        except Exception as e:
            session.rollback()  # In case of error, rollback the transaction
            return jsonify({
                "data": {},
                "message": f"An error occurred: {str(e)}",
                "status": "error"
            }), 500
        finally:
            session.close()  # Ensure the session is closed after the operation

    except Exception as e:
        return jsonify({
            "data": {},
            "message": f"An unexpected error occurred: {str(e)}",
            "status": "error"
        }), 500

# Get Role by ID
@role_blueprint.route("/<int:role_id>", methods=["GET"])
@jwt_required()
def get_role_by_id(role_id):
    try:
        # Get the session
        session = next(db_session())

        try:
            role = session.query(Role).filter_by(role_id=role_id).first()
            if not role:
                return jsonify({
                    "data": {},
                    "status": "error",
                    "message": "Role not found"
                }), 404

            return jsonify({
                "data": {
                    "role_id": role.role_id,
                    "role_name": role.role_name,
                    "role_description": role.role_description,
                    "created_at": role.created_at.isoformat(),
                    "updated_at": role.updated_at.isoformat()
                },
                "status": "success",
                "message": "Role retrieved successfully"
            }), 200
        except Exception as e:
            return jsonify({
                "data": {},
                "status": "error",
                "message": str(e)
            }), 500
        finally:
            session.close()  # Ensure the session is closed after the operation

    except Exception as e:
        return jsonify({
            "data": {},
            "status": "error",
            "message": str(e)
        }), 500

# Get All Roles
@role_blueprint.route("/", methods=["GET"])
@jwt_required()
def get_all_roles():
    try:
        # Get the session
        session = next(db_session())

        try:
            roles = session.query(Role).all()
            role_list = [{
                "role_id": role.role_id,
                "role_name": role.role_name,
                "role_description": role.role_description,
                "created_at": role.created_at.isoformat(),
                "updated_at": role.updated_at.isoformat()
            } for role in roles]

            return jsonify({
                "data": role_list,
                "status": "success",
                "message": "All roles retrieved successfully"
            }), 200

        except Exception as e:
            return jsonify({
                "data": {},
                "status": "error",
                "message": str(e)
            }), 500
        finally:
            session.close()  # Ensure the session is closed after the operation

    except Exception as e:
        return jsonify({
            "data": {},
            "status": "error",
            "message": str(e)
        }), 500
