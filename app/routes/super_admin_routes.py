from flask import Blueprint, request, jsonify, redirect, url_for, abort, flash, render_template
from app.models import db
from app.models.super_admin import SuperAdmin
from app.models.bot_plan import BotPlan
from app.models import Tenant, CustomBot
from app.database.DatabaseOperationPostgreSQL import db_session
from sqlalchemy.exc import IntegrityError
import logging
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt, get_jwt_identity
from sqlalchemy.sql import or_

logger = logging.getLogger(__name__)

super_admin_blueprint = Blueprint('super_admin', __name__)

@super_admin_blueprint.route("/register", methods=["POST"])
def create_superadmin():
    try:
        data = request.json
        required_fields = ["superadmin_username", "superadmin_email", "superadmin_password"]

        # Check if all required fields are present
        if not all(field in data for field in required_fields):
            return jsonify({
                "data": {},
                "message": "Missing required fields",
                "status": "error"
            }), 400

        # Get the session
        session = next(db_session())  # Assuming you have a session management in place

        try:
            # Check if the username or email already exists
            existing_superadmin = SuperAdmin.query.filter(
                (SuperAdmin.superadmin_username == data["superadmin_username"]) |
                (SuperAdmin.superadmin_email == data["superadmin_email"])
            ).first()

            if existing_superadmin:
                return jsonify({
                    "data": {},
                    "message": "Username or Email already exists",
                    "status": "error"
                }), 400

            # Hash the password before storing it
            hashed_password = generate_password_hash(data["superadmin_password"], method="pbkdf2:sha256")

            # Create a new SuperAdmin
            new_superadmin = SuperAdmin(
                superadmin_username=data["superadmin_username"],
                superadmin_email=data["superadmin_email"],
                superadmin_password=hashed_password
            )

            session.add(new_superadmin)
            session.commit()

            superadmin_id = new_superadmin.superadmin_id

            return jsonify({
                "data": {
                    "superadmin_id": superadmin_id
                },
                "message": "SuperAdmin registered successfully",
                "status": "success"
            }), 201
        except Exception as e:
            print(e)
            session.rollback()  # In case of error, rollback the transaction
            return jsonify({
                "data": {},
                "message": f"An error occurred: {str(e)}",
                "status": "error"
            }), 500
        finally:
            session.close()

    except Exception as e:
        print(e)
        return jsonify({
            "data": {},
            "message": f"An unexpected error occurred: {str(e)}",
            "status": "error"
        }), 500
        
        
@super_admin_blueprint.route("/login", methods=["POST"])
def superadmin_login():
    try:
        session = next(db_session())  # Get session instance
        data = request.json
        email = data.get("superadmin_email")
        password = data.get("superadmin_password")

        if not email or not password:
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Email and password are required"
            }), 400

        superadmin = session.query(SuperAdmin).filter_by(superadmin_email=email).first()
        
        if not superadmin:
            logger.error(f"SuperAdmin with email {email} not found.")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Invalid credentials"
            }), 401
        
        if not check_password_hash(superadmin.superadmin_password, password):
            logger.error(f"Password mismatch for email {email}.")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Invalid credentials"
            }), 401

        # Generate the access token with string identity and additional claims
        access_token = create_access_token(
            identity=str(superadmin.superadmin_id),  # Use superadmin_id as string
            additional_claims={"role": "superAdmin"}  # Add role as a claim
        )
        
        
        return jsonify({
            "data": {
                "superadmin_id": superadmin.superadmin_id,
                "access_token": access_token,
                "role":"superAdmin"
            },
            "status": "success",
            "message": "Login successful"
        }), 200

    except Exception as e:
        logger.exception(f"Error during login: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
    finally:
        session.close()


@super_admin_blueprint.route("/details", methods=["GET"])
@jwt_required()
def superadmin_details():
    try:
        session = next(db_session())
        superadmin_id = get_jwt_identity()
        jwt_data = get_jwt()
        logger.info(f"JWT Payload: {jwt_data}")  # Debug token payload
        if not superadmin_id:
            return jsonify({
                "data": {},
                "message": "Invalid token: superadmin_id not found",
                "status": "error"
            }), 401

        superadmin = session.query(SuperAdmin).filter_by(superadmin_id=superadmin_id).first()
        if not superadmin:
            logger.error(f"SuperAdmin with ID {superadmin_id} not found.")
            return jsonify({
                "data": {},
                "message": "SuperAdmin not found",
                "status": "error"
            }), 404

        role = jwt_data.get("role", "superAdmin")
        superadmin_data = {
            "superadmin_id": superadmin.superadmin_id,
            "superadmin_username": superadmin.superadmin_username,
            "superadmin_email": superadmin.superadmin_email,
            "role": role
        }

        return jsonify({
            "data": superadmin_data,
            "message": "SuperAdmin details retrieved successfully",
            "status": "success"
        }), 200

    except Exception as e:
        logger.exception(f"Error retrieving superadmin details: {str(e)}")
        return jsonify({
            "data": {},
            "message": f"An error occurred: {str(e)}",
            "status": "error"
        }), 500
    finally:
        session.close()


@super_admin_blueprint.route("/resource-counts", methods=["GET"])
@jwt_required()
def get_super_admin_resource_counts():
    try:
        # Check superadmin role
        claims = get_jwt()
        role = claims.get("role")
        if role != "superAdmin":
            logger.warning(f"Unauthorized access attempt by user with role: {role}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Unauthorized: Super admin access required"
            }), 403

        session = next(db_session())

        try:
            # Count all active tenants (del_flg = False or NULL)
            tenant_count = session.query(Tenant).filter(
                or_(Tenant.del_flg == False, Tenant.del_flg.is_(None))
            ).count()

            # Count all active bots (del_flg = False or NULL)
            bot_count = session.query(CustomBot).filter(
                or_(CustomBot.del_flg == False, CustomBot.del_flg.is_(None))
            ).count()

            # Count all active bot plans (del_flg = False or NULL)
            plan_count = session.query(BotPlan).filter(
                or_(BotPlan.del_flg == False, BotPlan.del_flg.is_(None))
            ).count()

            logger.info(f"Fetched resource counts: tenants={tenant_count}, bots={bot_count}, plans={plan_count}")
            return jsonify({
                "data": {
                    "tenants": tenant_count,
                    "bots": bot_count,
                    "plans": plan_count
                },
                "status": "success",
                "message": "Resource counts fetched successfully"
            }), 200

        except Exception as e:
            logger.exception(f"Error fetching superadmin resource counts: {str(e)}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }), 500

        finally:
            session.close()

    except Exception as e:
        logger.exception(f"Error initializing session: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": f"Error initializing session: {str(e)}"
        }), 500