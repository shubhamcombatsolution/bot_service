# app/routes/tenant_subscription.py

from flask import Blueprint, request, jsonify, g
from app.models import TenantSubscription, BotPlan, Tenant
from app.database.DatabaseOperationPostgreSQL import db_session
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime
import logging
from app.utils import can_send_message, update_remaining_messages, validate_full_subscription_status,check_create_agent,check_create_bot
from dateutil.parser import isoparse
from app.routes.helpers.access_control_decorator import authorize


subscription_blueprint = Blueprint("tenant_subscription", __name__)
logger = logging.getLogger(__name__)

def _parse_datetime(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        pass
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
    except Exception:
        pass
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


# @subscription_blueprint.route("/register", methods=["POST"])
# @jwt_required()
# def create_tenant_subscription():
#     try:
#         tenant_id = get_jwt_identity()
#         claims = get_jwt()
#         role = claims.get("role")
#         print("JWT Claims:", claims)
#         data = request.json

#         # Only check fields from request JSON
#         required_fields = ["plan_id", "subscription_start", "subscription_end"]
#         if not all(field in data for field in required_fields):
#             return jsonify({"data": {}, "message": "Missing required fields", "status": "error"}), 400

#         session = next(db_session())
#         try:
#             ALLOWED_ROLES = ["1", "superAdmin", "admin"]
#             if str(role) not in ALLOWED_ROLES:
#                 return jsonify({"data": {}, "message": "Unauthorized access", "status": "error"}), 403

#             tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
#             plan = session.query(BotPlan).filter_by(plan_id=data["plan_id"]).first()
#             if not tenant or not plan:
#                 return jsonify({"data": {}, "message": "Invalid tenant_id or plan_id", "status": "error"}), 400

#             # parse ISO 8601 datetimes safely
#             subscription_start = isoparse(data["subscription_start"])
#             subscription_end = isoparse(data["subscription_end"])

#             # Check for existing active subscription
#             existing = session.query(TenantSubscription).filter_by(
#                 tenant_id=tenant_id, subscription_status='active'
#             ).first()

#             if existing:
#                 return jsonify({"data": {}, "message": "Tenant already has an active subscription", "status": "error"}), 400

#             subscription = TenantSubscription(
#                 tenant_id=tenant_id,
#                 plan_id=data["plan_id"],
#                 subscription_start=subscription_start,
#                 subscription_end=subscription_end,
#                 auto_renewal=data.get("auto_renewal", False),
#                 remaining_msg=data.get("remaining_msg", 0),
#                 total_plan_msg=data.get("total_plan_msg", 0),
#                 subscription_status=data.get("subscription_status", "active")
#             )

#             session.add(subscription)
#             session.commit()

#             return jsonify({
#                 "data": {
#                     "subscription_id": subscription.subscription_id,
#                     "tenant_id": subscription.tenant_id,
#                     "plan_id": subscription.plan_id,
#                     "subscription_start": subscription.subscription_start,
#                     "subscription_end": subscription.subscription_end,
#                     "subscription_status": subscription.subscription_status
#                 },
#                 "message": "Tenant Subscription created successfully",
#                 "status": "success"
#             }), 201

#         except Exception as e:
#             session.rollback()
#             logger.error(f"Error creating subscription: {e}")
#             return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
#         finally:
#             session.close()

#     except Exception as e:
#         logger.error(f"Session error: {e}")
#         return jsonify({"data": {}, "message": str(e), "status": "error"}), 500

# @subscription_blueprint.route("/update/<int:subscription_id>", methods=["PUT"])
# @jwt_required()
# def update_tenant_subscription(subscription_id):
#     try:
#         # Get JWT claims
#         current_user = get_jwt_identity()   # tenant_id from JWT
#         claims = get_jwt()
#         role = claims.get("role")

#         data = request.json
#         required_fields = [
#             "plan_id", "subscription_start", "subscription_end",
#             "no_bot", "no_agent", "no_messages"
#         ]

#         # Find missing fields
#         missing_fields = [field for field in required_fields if field not in data]

#         if missing_fields:
#             return jsonify({
#                 "data": {},
#                 "message": f"Missing required fields: {', '.join(missing_fields)}",
#                 "status": "error"
#             }), 400

#         session = next(db_session())

#         try:
#             subscription = session.query(TenantSubscription).filter_by(
#                 subscription_id=subscription_id
#             ).first()

#             if not subscription:
#                 return jsonify({
#                     "data": {},
#                     "message": "Subscription not found",
#                     "status": "error"
#                 }), 404

#             # 🔹 Check tenant ownership if not superAdmin
#             if role != "superAdmin":
#                 jwt_tenant_id = str(current_user)
#                 if not jwt_tenant_id:
#                     return jsonify({
#                         "data": {},
#                         "message": "Tenant ID missing in token",
#                         "status": "error"
#                     }), 401
#                 if str(subscription.tenant_id) != jwt_tenant_id:
#                     return jsonify({
#                         "data": {},
#                         "message": "Unauthorized: Subscription does not belong to your tenant",
#                         "status": "error"
#                     }), 403

#             # Validate tenant & plan
#             tenant = session.query(Tenant).filter_by(tenant_id=subscription.tenant_id).first()
#             plan = session.query(BotPlan).filter_by(plan_id=data["plan_id"]).first()

#             if not tenant or not plan:
#                 return jsonify({
#                     "data": {},
#                     "message": "Invalid tenant_id or plan_id",
#                     "status": "error"
#                 }), 400
#             addAgent = data.get("no_agent")
#             # Update subscription
#             subscription.plan_id = data["plan_id"]
#             subscription.subscription_start = isoparse(data["subscription_start"])
#             subscription.subscription_end = isoparse(data["subscription_end"])
#             subscription.auto_renewal = data.get("auto_renewal", subscription.auto_renewal)
#             subscription.auto_renewal = data.get("auto_renewal", subscription.auto_renewal)
#             subscription.remaining_bots = data.get("no_bot", subscription.remaining_agent)
#             subscription.remaining_agent = addAgent
#             subscription.remaining_msg = data.get("remaining_msg", subscription.remaining_msg)
#             subscription.total_plan_msg = data.get("total_plan_msg", subscription.total_plan_msg)
#             subscription.subscription_status = data.get("subscription_status", subscription.subscription_status)
#             session.commit()

#             return jsonify({
#                 "data": {
#                     "subscription_id": subscription.subscription_id
#                 },
#                 "message": "Tenant Subscription updated successfully",
#                 "status": "success"
#             }), 200

#         except Exception as e:
#             session.rollback()
#             logger.error(f"Error updating subscription: {str(e)}")
#             return jsonify({
#                 "data": {},
#                 "message": f"An error occurred: {str(e)}",
#                 "status": "error"
#             }), 500
#         finally:
#             session.close()

#     except Exception as e:
#         logger.error(f"Error initializing session: {str(e)}")
#         return jsonify({
#             "data": {},
#             "message": f"Error initializing session: {str(e)}",
#             "status": "error"
#         }), 500

# @subscription_blueprint.route("/<int:tenant_id>", methods=["GET"])
# @jwt_required()
# def get_tenant_subscription_by_id(tenant_id):
#     try:
#         current_user = get_jwt_identity()
#         role = get_jwt().get("role")

#         session = next(db_session())
#         try:
#             if role != "superAdmin" and str(tenant_id) != str(current_user):
#                 return jsonify({"data": {}, "message": "Unauthorized tenant access", "status": "error"}), 403

#             subscription = session.query(TenantSubscription).filter_by(tenant_id=tenant_id).first()
#             if not subscription:
#                 return jsonify({"data": {}, "message": "Subscription not found", "status": "error"}), 404

#             return jsonify({
#                 "data": {
#                     "subscription_id": subscription.subscription_id,
#                     "tenant_id": subscription.tenant_id,
#                     "plan_id": subscription.plan_id,
#                     "subscription_start": subscription.subscription_start.isoformat() if subscription.subscription_start else None,
#                     "subscription_end": subscription.subscription_end.isoformat() if subscription.subscription_end else None,
#                     "auto_renewal": subscription.auto_renewal,
#                     "remaining_credits": subscription.remaining_msg,
#                     "total_plan_credits": subscription.total_plan_msg,
#                     "subscription_status": subscription.subscription_status,
#                     "del_flg": getattr(subscription, "del_flg", None)
#                 },
#                 "message": "Subscription retrieved successfully",
#                 "status": "success"
#             }), 200

#         except Exception as e:
#             logger.error(f"Query error: {e}")
#             return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
#         finally:
#             session.close()
#     except Exception as e:
#         logger.error(f"Session error: {e}")
#         return jsonify({"data": {}, "message": str(e), "status": "error"}), 500

# @subscription_blueprint.route("/", methods=["GET"])
# @jwt_required()
# def get_all_tenant_subscriptions():
#     try:
#         current_user = get_jwt_identity()
#         role = get_jwt().get("role")

#         session = next(db_session())
#         try:
#             if role == "superAdmin":
#                 subscriptions = session.query(TenantSubscription, BotPlan).join(BotPlan).all()
#             else:
#                 subscriptions = session.query(TenantSubscription, BotPlan).join(BotPlan).filter(
#                     TenantSubscription.tenant_id == current_user
#                 ).all()

#             results = []
#             for sub, plan in subscriptions:
#                 results.append({
#                     "planID": plan.plan_id,
#                     "planName": plan.plan_name,
#                     "planPrice": plan.plan_price,
#                     "planDuration": plan.plan_duration,
#                     "paymentStatus": plan.plan_status,
#                     "startDate": sub.subscription_start.isoformat() if sub.subscription_start else None,
#                     "endDate": sub.subscription_end.isoformat() if sub.subscription_end else None,
#                     "autoRenewal": sub.auto_renewal,
#                     "remainingCredits": sub.remaining_msg,
#                     "totalCredits": sub.total_plan_msg,
#                     "subscriptionStatus": sub.subscription_status,
#                     "del_flg": getattr(sub, "del_flg", None)
#                 })

#             return jsonify({
#                 "data": results,
#                 "message": "Tenant Subscriptions retrieved successfully",
#                 "status": "success"
#             }), 200

#         except Exception as e:
#             logger.error(f"Query error: {e}")
#             return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
#         finally:
#             session.close()

#     except Exception as e:
#         logger.error(f"Session error: {e}")
#         return jsonify({"data": {}, "message": str(e), "status": "error"}), 500

# @subscription_blueprint.route("/delete/<int:subscription_id>", methods=["DELETE"])
# @jwt_required()
# def delete_tenant_subscription(subscription_id):
#     try:
#         current_user = get_jwt_identity()
#         role = get_jwt().get("role")

#         session = next(db_session())
#         try:
#             subscription = session.query(TenantSubscription).filter_by(subscription_id=subscription_id).first()
#             if not subscription:
#                 return jsonify({"data": {}, "message": "Subscription not found", "status": "error"}), 404

#             if role != "superAdmin" and str(subscription.tenant_id) != str(current_user):
#                 return jsonify({"data": {}, "message": "Unauthorized tenant access", "status": "error"}), 403

#             session.delete(subscription)
#             session.commit()

#             return jsonify({
#                 "data": {"subscription_id": subscription_id},
#                 "message": "Tenant Subscription deleted successfully",
#                 "status": "success"
#             }), 200

#         except Exception as e:
#             session.rollback()
#             logger.error(f"Error deleting subscription: {e}")
#             return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
#         finally:
#             session.close()
#     except Exception as e:
#         logger.error(f"Session error: {e}")
#         return jsonify({"data": {}, "message": str(e), "status": "error"}), 500

@subscription_blueprint.route("/register", methods=["POST"])
@jwt_required()
@authorize(
    roles_allowed=["1", "admin", "superAdmin"],
    user_types_allowed=["admin"],
    allow_super_admin=True
)
def create_tenant_subscription():

    session = next(db_session())

    try:
        tenant_id = g.tenant.tenant_id if g.role != "superAdmin" else get_jwt_identity()
        data = request.json

        required_fields = ["plan_id", "subscription_start", "subscription_end"]
        if not all(field in data for field in required_fields):
            return jsonify({"data": {}, "message": "Missing required fields", "status": "error"}), 400

        tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        plan = session.query(BotPlan).filter_by(plan_id=data["plan_id"]).first()

        if not tenant or not plan:
            return jsonify({"data": {}, "message": "Invalid tenant_id or plan_id", "status": "error"}), 400

        subscription_start = isoparse(data["subscription_start"])
        subscription_end = isoparse(data["subscription_end"])

        existing = session.query(TenantSubscription).filter_by(
            tenant_id=tenant_id,
            subscription_status='active'
        ).first()

        if existing:
            return jsonify({"data": {}, "message": "Tenant already has an active subscription", "status": "error"}), 400

        subscription = TenantSubscription(
            tenant_id=tenant_id,
            plan_id=data["plan_id"],
            subscription_start=subscription_start,
            subscription_end=subscription_end,
            auto_renewal=data.get("auto_renewal", False),
            remaining_msg=data.get("remaining_msg", 0),
            total_plan_msg=data.get("total_plan_msg", 0),
            subscription_status=data.get("subscription_status", "active")
        )

        session.add(subscription)
        session.commit()

        return jsonify({
            "data": {
                "subscription_id": subscription.subscription_id,
                "tenant_id": subscription.tenant_id,
                "plan_id": subscription.plan_id,
                "subscription_start": subscription.subscription_start,
                "subscription_end": subscription.subscription_end,
                "subscription_status": subscription.subscription_status
            },
            "message": "Tenant Subscription created successfully",
            "status": "success"
        }), 201

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating subscription: {e}")
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
    finally:
        session.close()
        
@subscription_blueprint.route("/update/<int:subscription_id>", methods=["PUT"])
@jwt_required()
@authorize(
    roles_allowed=["admin", "superAdmin"],
    user_types_allowed=["admin"],
    allow_super_admin=True
)
def update_tenant_subscription(subscription_id):

    session = next(db_session())

    try:
        data = request.json or {}

        required_fields = [
            "plan_id", "subscription_start", "subscription_end",
            "no_bot", "no_agent", "no_messages"
        ]

        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return jsonify({
                "data": {},
                "message": f"Missing required fields: {', '.join(missing_fields)}",
                "status": "error"
            }), 400

        subscription = session.query(TenantSubscription).filter_by(
            subscription_id=subscription_id
        ).first()

        if not subscription:
            return jsonify({
                "data": {},
                "message": "Subscription not found",
                "status": "error"
            }), 404

        # -----------------------------------------
        # Tenant Ownership Validation
        # -----------------------------------------
        # SuperAdmin can update any subscription
        if g.role != "superAdmin":
            if not g.tenant or subscription.tenant_id != g.tenant.tenant_id:
                return jsonify({
                    "data": {},
                    "message": "Unauthorized: Subscription does not belong to your tenant",
                    "status": "error"
                }), 403

        # -----------------------------------------
        # Validate Tenant & Plan
        # -----------------------------------------
        tenant = session.query(Tenant).filter_by(
            tenant_id=subscription.tenant_id
        ).first()

        plan = session.query(BotPlan).filter_by(
            plan_id=data["plan_id"]
        ).first()

        if not tenant or not plan:
            return jsonify({
                "data": {},
                "message": "Invalid tenant_id or plan_id",
                "status": "error"
            }), 400

        # -----------------------------------------
        # Update Subscription
        # -----------------------------------------
        addAgent = data.get("no_agent")

        subscription.plan_id = data["plan_id"]
        subscription.subscription_start = isoparse(data["subscription_start"])
        subscription.subscription_end = isoparse(data["subscription_end"])
        subscription.auto_renewal = data.get("auto_renewal", subscription.auto_renewal)
        subscription.remaining_bots = data.get("no_bot", subscription.remaining_bots)
        subscription.remaining_agent = addAgent
        subscription.remaining_msg = data.get("remaining_msg", subscription.remaining_msg)
        subscription.total_plan_msg = data.get("total_plan_msg", subscription.total_plan_msg)
        subscription.subscription_status = data.get(
            "subscription_status",
            subscription.subscription_status
        )

        session.commit()

        return jsonify({
            "data": {
                "subscription_id": subscription.subscription_id
            },
            "message": "Tenant Subscription updated successfully",
            "status": "success"
        }), 200

    except Exception as e:
        session.rollback()
        logger.error(f"Error updating subscription: {str(e)}")
        return jsonify({
            "data": {},
            "message": f"An error occurred: {str(e)}",
            "status": "error"
        }), 500

    finally:
        session.close()


@subscription_blueprint.route("/<int:tenant_id>", methods=["GET"])
@jwt_required()
@authorize(
    roles_allowed=["admin", "superAdmin"],
    user_types_allowed=["admin"],
    allow_super_admin=True
)
def get_tenant_subscription_by_id(tenant_id):

    session = next(db_session())

    try:
        if g.role != "superAdmin" and g.tenant.tenant_id != tenant_id:
            return jsonify({"data": {}, "message": "Unauthorized tenant access", "status": "error"}), 403

        subscription = session.query(TenantSubscription).filter_by(
            tenant_id=tenant_id
        ).first()

        if not subscription:
            return jsonify({"data": {}, "message": "Subscription not found", "status": "error"}), 404

        return jsonify({
            "data": {
                "subscription_id": subscription.subscription_id,
                "tenant_id": subscription.tenant_id,
                "plan_id": subscription.plan_id,
                "subscription_start": subscription.subscription_start.isoformat() if subscription.subscription_start else None,
                "subscription_end": subscription.subscription_end.isoformat() if subscription.subscription_end else None,
                "auto_renewal": subscription.auto_renewal,
                "remaining_credits": subscription.remaining_msg,
                "total_plan_credits": subscription.total_plan_msg,
                "subscription_status": subscription.subscription_status,
                "del_flg": getattr(subscription, "del_flg", None)
            },
            "message": "Subscription retrieved successfully",
            "status": "success"
        }), 200

    except Exception as e:
        logger.error(f"Query error: {e}")
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
    finally:
        session.close()



@subscription_blueprint.route("/", methods=["GET"])
@jwt_required()
@authorize(
    roles_allowed=["admin", "superAdmin"],
    user_types_allowed=["admin"],
    allow_super_admin=True
)
def get_all_tenant_subscriptions():

    session = next(db_session())

    try:
        if g.role == "superAdmin":
            subscriptions = session.query(TenantSubscription, BotPlan).join(BotPlan).all()
        else:
            subscriptions = session.query(TenantSubscription, BotPlan).join(BotPlan).filter(
                TenantSubscription.tenant_id == g.tenant.tenant_id
            ).all()

        results = []
        for sub, plan in subscriptions:
            results.append({
                "planID": plan.plan_id,
                "planName": plan.plan_name,
                "planPrice": plan.plan_price,
                "planDuration": plan.plan_duration,
                "paymentStatus": plan.plan_status,
                "startDate": sub.subscription_start.isoformat() if sub.subscription_start else None,
                "endDate": sub.subscription_end.isoformat() if sub.subscription_end else None,
                "autoRenewal": sub.auto_renewal,
                "remainingCredits": sub.remaining_msg,
                "totalCredits": sub.total_plan_msg,
                "subscriptionStatus": sub.subscription_status,
                "del_flg": getattr(sub, "del_flg", None)
            })

        return jsonify({
            "data": results,
            "message": "Tenant Subscriptions retrieved successfully",
            "status": "success"
        }), 200

    except Exception as e:
        logger.error(f"Query error: {e}")
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
    finally:
        session.close()


@subscription_blueprint.route("/delete/<int:subscription_id>", methods=["DELETE"])
@jwt_required()
@authorize(
    roles_allowed=["admin", "superAdmin"],
    user_types_allowed=["admin"],
    allow_super_admin=True
)
def delete_tenant_subscription(subscription_id):

    session = next(db_session())

    try:
        subscription = session.query(TenantSubscription).filter_by(
            subscription_id=subscription_id
        ).first()

        if not subscription:
            return jsonify({"data": {}, "message": "Subscription not found", "status": "error"}), 404

        if g.role != "superAdmin" and subscription.tenant_id != g.tenant.tenant_id:
            return jsonify({"data": {}, "message": "Unauthorized tenant access", "status": "error"}), 403

        session.delete(subscription)
        session.commit()

        return jsonify({
            "data": {"subscription_id": subscription_id},
            "message": "Tenant Subscription deleted successfully",
            "status": "success"
        }), 200

    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting subscription: {e}")
        return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
    finally:
        session.close()



@subscription_blueprint.route('/subscription/<int:tenant_id>/can_send', methods=['GET'])
@jwt_required()
def check_can_send(tenant_id):
    session = next(db_session())
    try:
        success, result = can_send_message(session, tenant_id)
        return jsonify(result), 200 if success else 400
    finally:
        session.close()

@subscription_blueprint.route('/subscription/<int:tenant_id>/deduct', methods=['POST'])
@jwt_required()
def deduct_messages(tenant_id):
    session = next(db_session())
    try:
        data = request.get_json()
        message_count = int(data.get('message_count', 1))
    except Exception:
        session.close()
        return jsonify({"error_code": "INVALID_PAYLOAD", "message": "Invalid request body."}), 400

    try:
        success, result = update_remaining_messages(session, tenant_id, message_count)
        return jsonify(result), 200 if success else 400
    finally:
        session.close()

@subscription_blueprint.route('/subscription/<int:tenant_id>/remaining', methods=['GET'])
@jwt_required()
def get_remaining_messages(tenant_id):
    session = next(db_session())
    try:
        sub = session.query(TenantSubscription).filter_by(tenant_id=tenant_id, subscription_status='active').first()
        if not sub:
            return jsonify({
                "error_code": "NO_ACTIVE_SUBSCRIPTION",
                "message": "No active subscription found."
            }), 404

        return jsonify({
            "remaining_msg": sub.remaining_msg,
            "subscription_end": sub.subscription_end.isoformat() if sub.subscription_end else None
        }), 200

    except Exception as e:
        session.rollback()
        return jsonify({"error_code": "SERVER_ERROR", "message": str(e)}), 500
    finally:
        session.close()

@subscription_blueprint.route('/subscription/<int:tenant_id>/validate', methods=['GET'])
@jwt_required()
def validate_subscription(tenant_id):
    session = next(db_session())
    try:
        sub = session.query(TenantSubscription).filter_by(
            tenant_id=tenant_id,
            subscription_status='active',
            del_flg=False
        ).first()

        if not sub:
            return jsonify({
                "valid": False,
                "message": "No active subscription found"
            }), 404

        plan = session.query(BotPlan).filter_by(
            plan_id=sub.plan_id,
            plan_status=True,
            del_flg=False
        ).first()

        if not plan:
            return jsonify({
                "valid": False,
                "message": "Invalid or inactive plan"
            }), 400

        result = {
            "valid": True,
            "message": "Subscription is valid",
            "subscription": {
                "subscription_id": sub.subscription_id,
                "tenant_id": sub.tenant_id,
                "plan_id": sub.plan_id,
                "subscription_start": sub.subscription_start.isoformat() if sub.subscription_start else None,
                "subscription_end": sub.subscription_end.isoformat() if sub.subscription_end else None,
                "auto_renewal": sub.auto_renewal,
                "remaining_credits": sub.remaining_msg,
                "total_plan_credits": sub.total_plan_msg,
                "subscription_status": sub.subscription_status
            },
            "plan": {
                "plan_id": plan.plan_id,
                "plan_name": plan.plan_name,
                "plan_description": plan.plan_description,
                "plan_price": plan.plan_price,
                "plan_duration": plan.plan_duration,
                "plan_messages": plan.plan_messages,
                "no_bot": plan.no_bot,
                "no_agent": plan.no_agent,
                "message_rollover": plan.message_rollover,
                "overage_limit": plan.overage_limit,
            }
        }

        return jsonify(result), 200

    except Exception as e:
        session.rollback()
        return jsonify({"valid": False, "message": str(e)}), 500
    finally:
        session.close()


@subscription_blueprint.route("/check_limit/agent", methods=["GET"])
@jwt_required()
def can_create_agent():
    session = next(db_session())
    try:
        # Extract tenant_id from JWT claims
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return jsonify({
                "status": False,
                "error_code": "TENANT_ID_MISSING",
                "message": "Tenant ID not found in token."
            }), 401

        status, response = check_create_agent(session, tenant_id)
        return jsonify({"status": status, **response}), (200 if status else 403)

    except Exception as e:
        return jsonify({
            "status": False,
            "error_code": "INTERNAL_ERROR",
            "message": str(e)
        }), 500


@subscription_blueprint.route("/check_limit/bot", methods=["GET"])
@jwt_required()
def can_create_bot():
    session = next(db_session())

    try:
        # Extract tenant_id from JWT claims
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return jsonify({
                "status": False,
                "error_code": "TENANT_ID_MISSING",
                "message": "Tenant ID not found in token."
            }), 401

        status, response = check_create_bot(session, tenant_id)
        return jsonify({"status": status, **response}), (200 if status else 403)

    except Exception as e:
        return jsonify({
            "status": False,
            "error_code": "INTERNAL_ERROR",
            "message": str(e)
        }), 500
