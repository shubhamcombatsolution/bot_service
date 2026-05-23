from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from app.models import BotPlan
from app.database.DatabaseOperationPostgreSQL import db_session
import logging

logger = logging.getLogger(__name__)
bot_plan_blueprint = Blueprint("bot-plan", __name__)

ALLOWED_PLAN_FIELDS = {
    "plan_name",
    "plan_description",
    "plan_price",
    "plan_duration",
    "plan_status",
    "payment_status",
    "plan_messages",
    "no_bot",
    "no_agent",
    "message_rollover",
    "overage_limit",
}

@bot_plan_blueprint.route("/register", methods=["POST"])
@jwt_required()
def create_bot_plan():
    try:
        # Check superadmin role
        claims = get_jwt()
        role = claims.get("role")
        if role != "superAdmin":
            logger.warning(f"Unauthorized access attempt by user with role: {role}")
            return jsonify({
                "data": {},
                "message": "Unauthorized: Super admin access required",
                "status": "error"
            }), 403

        data = request.json or {}
        required_fields = ["plan_name", "plan_price", "plan_duration"]

        unknown_fields = sorted(set(data.keys()) - ALLOWED_PLAN_FIELDS)
        if unknown_fields:
            return jsonify({
                "data": {},
                "message": f"Unknown fields: {', '.join(unknown_fields)}",
                "status": "error"
            }), 400

        # Check if all required fields are present
        if not all(field in data for field in required_fields):
            return jsonify({
                "data": {},
                "message": "Missing required fields",
                "status": "error"
            }), 400

        session = next(db_session())

        try:
            # Create a new bot plan
            # new_plan = BotPlan(
            #     plan_name=data["plan_name"],
            #     plan_description=data.get("plan_description", ""),
            #     plan_price=data["plan_price"],
            #     plan_duration=data["plan_duration"],
            #     plan_status=data.get("plan_status", True),
            #     payment_status=data.get("payment_status", "pending")
            # )
            new_plan = BotPlan(
                plan_name = data["plan_name"],
                plan_description = data.get("plan_description", ""),
                plan_price = float(data["plan_price"]),
                plan_duration = int(data["plan_duration"]),
                plan_status = bool(data.get("plan_status", True)),
                plan_messages = int(data.get("plan_messages") or 0),
                no_bot = int(data.get("no_bot") or 0),
                no_agent = int(data.get("no_agent") or 0),
                message_rollover = bool(data.get("message_rollover", False)),
                overage_limit = int(data.get("overage_limit") or 0),
                payment_status = data.get("payment_status", "pending")
            )
            session.add(new_plan)
            session.commit()

            logger.info(f"Bot Plan {new_plan.plan_id} created successfully")
            return jsonify({
                "data": {
                    "plan_id": new_plan.plan_id
                },
                "message": "Bot Plan created successfully",
                "status": "success"
            }), 201

        except Exception as e:
            session.rollback()
            logger.error(f"Error creating bot plan: {str(e)}")
            return jsonify({
                "data": {},
                "message": f"An error occurred: {str(e)}",
                "status": "error"
            }), 500

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error initializing session: {str(e)}")
        return jsonify({
            "data": {},
            "message": f"Error initializing session: {str(e)}",
            "status": "error"
        }), 500

@bot_plan_blueprint.route("/update/<int:plan_id>", methods=["PUT"])
@jwt_required()
def update_bot_plan(plan_id):
    try:
        # Check superadmin role
        claims = get_jwt()
        role = claims.get("role")
        logger.info(f"role {role} status ")
        if role != "superAdmin":
            logger.warning(f"Unauthorized access attempt by user with role: {role}")
            return jsonify({
                "data": {},
                "message": "Unauthorized: Super admin access required",
                "status": "error"
            }), 403

        data = request.json or {}

        unknown_fields = sorted(set(data.keys()) - ALLOWED_PLAN_FIELDS)
        if unknown_fields:
            return jsonify({
                "data": {},
                "message": f"Unknown fields: {', '.join(unknown_fields)}",
                "status": "error"
            }), 400

        session = next(db_session())

        try:
            # Find the existing bot plan by ID
            existing_plan = session.query(BotPlan).filter_by(plan_id=plan_id).first()

            if not existing_plan:
                return jsonify({
                    "data": {},
                    "message": "Bot Plan not found",
                    "status": "error"
                }), 404

            # Update only provided fields
            if "plan_name" in data:
                existing_plan.plan_name = data["plan_name"]
            if "plan_description" in data:
                existing_plan.plan_description = data["plan_description"]
            if "plan_price" in data:
                existing_plan.plan_price = float(data["plan_price"])
            if "plan_duration" in data:
                existing_plan.plan_duration = int(data["plan_duration"])
            if "plan_status" in data:
                existing_plan.plan_status = bool(data["plan_status"])
            if "plan_messages" in data:
                existing_plan.plan_messages = int(data["plan_messages"] or 0)
            if "no_bot" in data:
                existing_plan.no_bot = int(data["no_bot"] or 0)
            if "no_agent" in data:
                existing_plan.no_agent = int(data["no_agent"] or 0)
            if "overage_limit" in data:
                existing_plan.overage_limit = int(data["overage_limit"] or 0)
            if "message_rollover" in data:
                existing_plan.message_rollover = bool(data["message_rollover"])
            if "payment_status" in data:
                existing_plan.payment_status = data["payment_status"]

            session.commit()

            logger.info(f"Bot Plan {plan_id} updated successfully")
            return jsonify({
                "data": {
                    "plan_id": existing_plan.plan_id
                },
                "message": "Bot Plan updated successfully",
                "status": "success"
            }), 200

        except Exception as e:
            session.rollback()
            logger.error(f"Error updating bot plan: {str(e)}")
            return jsonify({
                "data": {},
                "message": f"An error occurred: {str(e)}",
                "status": "error"
            }), 500

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error initializing session: {str(e)}")
        return jsonify({
            "data": {},
            "message": f"Error initializing session: {str(e)}",
            "status": "error"
        }), 500

@bot_plan_blueprint.route("/<int:plan_id>", methods=["GET"])
@jwt_required()
def get_bot_plan_by_id(plan_id):
    try:
        # Check superadmin role
        claims = get_jwt()
        role = claims.get("role")
        if role != "superAdmin":
            logger.warning(f"Unauthorized access attempt by user with role: {role}")
            return jsonify({
                "data": {},
                "message": "Unauthorized: Super admin access required",
                "status": "error"
            }), 403

        session = next(db_session())

        try:
            # Filter by plan_id and del_flg=False
            plan = session.query(BotPlan).filter_by(plan_id=plan_id, del_flg=False).first()
            if not plan:
                return jsonify({
                    "data": {},
                    "status": "error",
                    "message": "Bot Plan not found"
                }), 404

            logger.info(f"Bot Plan {plan_id} retrieved successfully")
            return jsonify({
                "data": {
                    "plan_id": plan.plan_id,
                    "plan_name": plan.plan_name,
                    "plan_description": plan.plan_description,
                    "plan_price": str(plan.plan_price),
                    "plan_duration": plan.plan_duration,
                    "payment_status": plan.payment_status,
                    "created_at": plan.created_at.isoformat(),
                    "updated_at": plan.updated_at.isoformat()
                },
                "status": "success",
                "message": "Bot Plan retrieved successfully"
            }), 200

        except Exception as e:
            logger.error(f"Error retrieving bot plan: {str(e)}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }), 500

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error initializing session: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": f"Error initializing session: {str(e)}"
        }), 500

@bot_plan_blueprint.route("/", methods=["GET"])
@jwt_required()
def get_all_bot_plans():
    try:
        session = next(db_session())

        try:
            # Query plans where del_flg is False or NULL (if applicable)
            plans = session.query(BotPlan).filter((BotPlan.del_flg == False) | (BotPlan.del_flg.is_(None))).all()
            logger.debug(f"Retrieved {len(plans)} plans from database: {[plan.plan_id for plan in plans]}")
            
            plan_list = [{
                "plan_id": plan.plan_id,
                "plan_name": plan.plan_name,
                "plan_description": plan.plan_description,
                "plan_price": str(plan.plan_price),
                "plan_duration": plan.plan_duration,
                "plan_status": plan.plan_status,
                "payment_status": plan.payment_status,
                "no_bot": plan.no_bot,
                "plan_messages": plan.plan_messages, 
                "no_agent": plan.no_agent,
                "overage_limit": plan.overage_limit,
                "message_rollover": plan.message_rollover,
                "created_at": plan.created_at.isoformat(),
                "updated_at": plan.updated_at.isoformat(),
                "del_flg": plan.del_flg  # Include for debugging
            } for plan in plans]

            logger.info(f"Retrieved {len(plan_list)} bot plans successfully")
            return jsonify({
                "data": plan_list,
                "status": "success",
                "message": "All Bot Plans retrieved successfully"
            }), 200

        except Exception as e:
            logger.error(f"Error retrieving bot plans: {str(e)}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }), 500

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error initializing session: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": f"Error initializing session: {str(e)}"
        }), 500

@bot_plan_blueprint.route('/update-status/<int:plan_id>', methods=['PUT'])
@jwt_required()
def update_plan_status(plan_id):
    try:
        # Check superadmin role
        claims = get_jwt()
        role = claims.get("role")
        if role != "superAdmin":
            logger.warning(f"Unauthorized access attempt by user with role: {role}")
            return jsonify({
                "data": {},
                "message": "Unauthorized: Super admin access required",
                "status": "error"
            }), 403

        data = request.json
        session = next(db_session())

        try:
            plan = session.query(BotPlan).get(plan_id)
            if not plan:
                return jsonify({
                    "data": {},
                    "message": "Bot Plan not found",
                    "status": "error"
                }), 404

            # Convert string to boolean
            if 'plan_status' in data:
                plan.plan_status = str(data['plan_status']).lower() in ['true', '1', 'yes']

            session.commit()
            logger.info(f"Bot Plan {plan_id} status updated successfully")
            return jsonify({
                "data": {
                    "plan_id": plan.plan_id
                },
                "message": "Bot Plan status updated successfully",
                "status": "success"
            }), 200

        except Exception as e:
            session.rollback()
            logger.error(f"Error updating bot plan status: {str(e)}")
            return jsonify({
                "data": {},
                "message": f"An error occurred: {str(e)}",
                "status": "error"
            }), 500

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error initializing session: {str(e)}")
        return jsonify({
            "data": {},
            "message": f"Error initializing session: {str(e)}",
            "status": "error"
        }), 500

@bot_plan_blueprint.route("/<int:plan_id>", methods=["DELETE"])
@jwt_required()
def delete_bot_plan(plan_id):
    try:
        # Check superadmin role
        claims = get_jwt()
        role = claims.get("role")
        if role != "superAdmin":
            logger.warning(f"Unauthorized access attempt by user with role: {role}")
            return jsonify({
                "data": {},
                "message": "Unauthorized: Super admin access required",
                "status": "error"
            }), 403

        session = next(db_session())

        try:
            plan = session.query(BotPlan).filter_by(plan_id=plan_id).first()
            if not plan:
                return jsonify({
                    "data": {},
                    "message": "Bot Plan not found",
                    "status": "error"
                }), 404

            # Perform soft delete by setting del_flg to True
            plan.del_flg = True
            session.commit()

            logger.info(f"Bot Plan {plan_id} deleted successfully")
            return jsonify({
                "data": {},
                "message": "Bot Plan deleted successfully",
                "status": "success"
            }), 200

        except Exception as e:
            session.rollback()
            logger.error(f"Error soft deleting bot plan: {str(e)}")
            return jsonify({
                "data": {},
                "message": f"An error occurred: {str(e)}",
                "status": "error"
            }), 500

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error initializing session: {str(e)}")
        return jsonify({
            "data": {},
            "message": f"Error initializing session: {str(e)}",
            "status": "error"
        }), 500
