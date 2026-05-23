from flask import Blueprint, request, jsonify
from app.models.tenant import Tenant
from app.models.bot_plan import BotPlan
from app.models.tenant_payment_info import tenant_payment_info
from app.database.DatabaseOperationPostgreSQL import db_session
from flask_jwt_extended import create_access_token, jwt_required, unset_jwt_cookies, get_jwt_identity, get_jwt
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime, timedelta
from app.services.prebuilt_agent_service import PrebuiltAgentService


tenant_blueprint = Blueprint("tenant", __name__)
logger = logging.getLogger(__name__)


def _send_tenant_status_email(to_addr: str, tenant_name: str, tenant_status: str) -> None:
    normalized_status = (tenant_status or "").strip().lower()
    if normalized_status == "active":
        status_line = "Your account has been activated. Please check and login."
    elif normalized_status == "inactive":
        status_line = (
            "Your account is inactive. If you want to activate your account, "
            "please contact our team."
        )
    else:
        status_line = f"Your account status has been updated to: {tenant_status}."

    msg = EmailMessage()
    msg["Subject"] = f"Your account is now {tenant_status}"
    msg["From"] = os.environ.get("SMTP_FROM")
    msg["To"] = to_addr
    msg.set_content(
        f"""Hi {tenant_name or 'Tenant'},

{status_line}

Thanks,
Support Team
"""
    )

    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls(context=context)
        server.login(os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS"))
        server.send_message(msg)

@tenant_blueprint.route("/register", methods=["POST"])
def create_tenant():
    try:
        data = request.json
        required_fields = ["tenant_name", "tenant_key", "tenant_emailid", "tenant_contact", "tenant_address", "plan_id"]
        
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
            # Check if the provided plan_id exists in the BotPlan table
            plan = session.query(BotPlan).filter_by(plan_id=data["plan_id"]).first()
            if not plan:
                return jsonify({
                    "data": {},
                    "message": "Invalid plan_id provided",
                    "status": "error"
                }), 400

            # Create new tenant
            new_tenant = Tenant(
                tenant_name=data["tenant_name"],
                tenant_key=data["tenant_key"],
                tenant_emailid=data["tenant_emailid"],
                tenant_contact=data["tenant_contact"],
                tenant_address=data["tenant_address"],
                tenant_city=data.get("tenant_city", None),
                tenant_country=data.get("tenant_country", None),
                tenant_postcode=data.get("tenant_postcode", None),
                tenant_GSTNo=data.get("tenant_GSTNo", None),
                tenant_PAN=data.get("tenant_PAN", None),
                tenant_status=data.get("tenant_status", "Active"),
                tenant_plan_id=data["plan_id"],  # Associate the plan_id here
                del_flg=data.get("del_flg", False)
            )

            session.add(new_tenant)
            session.commit()

            tenant_id = new_tenant.tenant_id

            # ── Auto-grant all active prebuilt agents to the new tenant ──
            try:
                PrebuiltAgentService().grant_prebuilt_agents_to_tenant(
                    tenant_id=tenant_id,
                    plan=str(data.get("plan_id", ""))
                )
                logger.info("Prebuilt agents granted to new tenant %d", tenant_id)
            except Exception as grant_err:
                logger.warning("Could not grant prebuilt agents to tenant %d: %s", tenant_id, grant_err)
                # Non-fatal — tenant registration still succeeds

            return jsonify({
                "data": {
                    "tenant_id": tenant_id
                },
                "message": "Tenant registered successfully",
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


@tenant_blueprint.route("/update", methods=["POST"])
@jwt_required()
def update_tenant():
    session = None
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "data": {},
                "message": "No data provided",
                "status": "error"
            }), 400

        required_fields = ["tenant_id", "tenant_name", "tenant_emailid", "tenant_contact", "tenant_address"]
        
        # Check if all required fields are present
        if not all(field in data for field in required_fields):
            # Log missing fields for debugging (optional)
            print("Received data:", data)
            return jsonify({
                "data": {},
                "message": "Missing required fields",
                "status": "error"
            }), 400

        # Get the session
        session = next(db_session())

        # Check if tenant exists by tenant_id
        existing_tenant = session.query(Tenant).filter_by(tenant_id=data["tenant_id"]).first()
        if not existing_tenant:
            return jsonify({
                "data": {},
                "message": "Tenant not found",
                "status": "error"
            }), 404

        # Update existing tenant details
        existing_tenant.tenant_name = data["tenant_name"]
        existing_tenant.tenant_emailid = data["tenant_emailid"]
        existing_tenant.tenant_contact = data["tenant_contact"]
        existing_tenant.tenant_address = data["tenant_address"]
        existing_tenant.tenant_city = data.get("tenant_city", existing_tenant.tenant_city)
        existing_tenant.tenant_country = data.get("tenant_country", existing_tenant.tenant_country)
        existing_tenant.tenant_postcode = data.get("tenant_postcode", existing_tenant.tenant_postcode)
        existing_tenant.tenant_GSTNo = data.get("tenant_GSTNo", existing_tenant.tenant_GSTNo)
        existing_tenant.tenant_PAN = data.get("tenant_PAN", existing_tenant.tenant_PAN)
        existing_tenant.tenant_status = data.get("tenant_status", existing_tenant.tenant_status)
        existing_tenant.del_flg = data.get("del_flg", existing_tenant.del_flg)

        session.commit()

        return jsonify({
            "data": {
                "tenant_id": existing_tenant.tenant_id,
                "tenant_name": existing_tenant.tenant_name,
                "tenant_emailid": existing_tenant.tenant_emailid
            },
            "message": "Tenant information updated successfully",
            "status": "success"
        }), 200

    except Exception as e:
        print(f"Error: {str(e)}")  # Log the error for debugging
        if session:
            session.rollback()
        return jsonify({
            "data": {},
            "message": f"An error occurred: {str(e)}",
            "status": "error"
        }), 500
    finally:
        if session:
            session.close()



# Get Tenant by ID
@tenant_blueprint.route("/<int:tenant_id>", methods=["GET"])
@jwt_required()
def get_tenant_by_id(tenant_id):
    try:
        # Get the session
        session = next(db_session())

        try:
            tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                return jsonify({
                    "data": {},
                    "status": "error",
                    "message": "Tenant not found"
                }), 404

            return jsonify({
                "data": {
                    "tenant_id": tenant.tenant_id,
                    "tenant_name": tenant.tenant_name,
                    "tenant_emailid": tenant.tenant_emailid,
                    "tenant_contact": tenant.tenant_contact,
                    "tenant_address": tenant.tenant_address,
                    "tenant_city": tenant.tenant_city,
                    "tenant_country": tenant.tenant_country,
                    "tenant_postcode": tenant.tenant_postcode,
                    "tenant_GSTNo": tenant.tenant_GSTNo,
                    "tenant_PAN": tenant.tenant_PAN,
                    "tenant_status": tenant.tenant_status,
                    "del_flg": tenant.del_flg,
                    "created_at": tenant.created_at.isoformat()
                },
                "status": "success",
                "message": "Tenant retrieved successfully"
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



# # Get All Tenants
# @tenant_blueprint.route("/", methods=["GET"])
# @jwt_required()
# def get_all_tenants():
#     try:
#         # Get the current user's identity from JWT
#         current_user = get_jwt_identity()
#         claims = get_jwt()  # Access additional claims
#         tenant_id = claims.get("tenant_id")
#         role = claims.get("role")
#         if role != 'superAdmin':
#             logger.warning(f"Unauthorized access attempt by user with role: {role}")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Unauthorized: Super admin access required"
#             }), 403

#         # Get query parameter to include deleted tenants (optional)
#         include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'

#         # Start database session
#         session = next(db_session())

#         try:
#             # Query tenants with a left join to BotPlan (handles null tenant_plan_id)
#             query = session.query(Tenant, BotPlan.plan_name).outerjoin(
#                 BotPlan, BotPlan.plan_id == Tenant.tenant_plan_id
#             )
#             if not include_deleted:
#                 query = query.filter(Tenant.del_flg == False)  # Exclude deleted tenants by default

#             tenants = query.all()

#             # Build tenant list
#             tenant_list = [{
#                 "tenant_id": tenant.Tenant.tenant_id,
#                 "tenant_name": tenant.Tenant.tenant_name,
#                 "tenant_emailid": tenant.Tenant.tenant_emailid,
#                 "tenant_contact": tenant.Tenant.tenant_contact,
#                 "tenant_address": tenant.Tenant.tenant_address,
#                 "tenant_city": tenant.Tenant.tenant_city,
#                 "tenant_country": tenant.Tenant.tenant_country,
#                 "tenant_postcode": tenant.Tenant.tenant_postcode,
#                 "tenant_GSTNo": tenant.Tenant.tenant_GSTNo,
#                 "tenant_PAN": tenant.Tenant.tenant_PAN,
#                 "tenant_status": tenant.Tenant.tenant_status,
#                 "tenant_plan_id": tenant.Tenant.tenant_plan_id,
#                 "tenant_plan_name": tenant.plan_name,
#                 "del_flg": tenant.Tenant.del_flg,
#                 "created_at": tenant.Tenant.created_at.isoformat()
#             } for tenant in tenants]

#             logger.info(f"Retrieved {len(tenant_list)} tenants successfully")
#             return jsonify({
#                 "data": tenant_list,
#                 "status": "success",
#                 "message": "All tenants retrieved successfully"
#             }), 200

#         except Exception as e:
#             logger.error(f"Database query error: {str(e)}")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": f"Failed to retrieve tenants: {str(e)}"
#             }), 500

#         finally:
#             session.close()

#     except Exception as e:
#         logger.error(f"Session initialization error: {str(e)}")
#         return jsonify({
#             "data": {},
#             "status": "error",
#             "message": f"Internal server error: {str(e)}"
#         }), 500


@tenant_blueprint.route("/", methods=["GET"])
@jwt_required()
def get_all_tenants():
    try:
        # Get the current user's identity from JWT
        current_user = get_jwt_identity()
        claims = get_jwt()  # Access additional claims
        tenant_id = claims.get("tenant_id")
        role = claims.get("role")
        if role != 'superAdmin':
            logger.warning(f"Unauthorized access attempt by user with role: {role}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Unauthorized: Super admin access required"
            }), 403

        # Get query parameter to include deleted tenants (optional)
        include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'

        # Start database session
        session = next(db_session())

        try:
            # Query tenants with a left join to BotPlan
            query = session.query(Tenant, BotPlan.plan_name, BotPlan.plan_duration).outerjoin(
                BotPlan, BotPlan.plan_id == Tenant.tenant_plan_id
            )
            if not include_deleted:
                query = query.filter(Tenant.del_flg == False)  # Exclude deleted tenants

            tenants = query.all()
            tenant_list = []

            today = datetime.now().date()

            for tenant, plan_name, plan_duration in tenants:
                # Fetch the most recent active plan from tenant_payment_info
                payment_plan = (
                    session.query(tenant_payment_info)
                    .filter_by(tenant_id=tenant.tenant_id, status="success", del_flg=False)
                    .order_by(tenant_payment_info.created_at.desc())
                    .first()
                )

                plan_info = {}
                if payment_plan:
                    # Use payment plan details if available
                    plan_info = {
                        "tenant_plan_name": payment_plan.plans,
                        "tenant_plan_id": None,  # Payment plans may not map directly to BotPlan
                        "from_date": payment_plan.from_date.strftime("%Y-%m-%d") if isinstance(payment_plan.from_date, datetime) else str(payment_plan.from_date),
                        "end_date": payment_plan.end_date.strftime("%Y-%m-%d") if isinstance(payment_plan.end_date, datetime) else str(payment_plan.end_date),
                        "payment_mode": payment_plan.payment_mode
                    }
                elif tenant.tenant_plan_id:
                    # Fallback to BotPlan if no payment plan exists
                    from_date = datetime.now()
                    end_date = from_date + timedelta(days=plan_duration * 30)  # Approximate months to days
                    plan_info = {
                        "tenant_plan_name": plan_name,
                        "tenant_plan_id": tenant.tenant_plan_id,
                        "from_date": from_date.strftime("%Y-%m-%d"),
                        "end_date": end_date.strftime("%Y-%m-%d"),
                        "payment_mode": "Monthly" if plan_duration <= 1 else "Yearly"
                    }
                else:
                    # No plan assigned or purchased
                    plan_info = {
                        "tenant_plan_name": None,
                        "tenant_plan_id": None,
                        "from_date": None,
                        "end_date": None,
                        "payment_mode": None
                    }

                tenant_list.append({
                    "tenant_id": tenant.tenant_id,
                    "tenant_name": tenant.tenant_name,
                    "tenant_emailid": tenant.tenant_emailid,
                    "tenant_contact": tenant.tenant_contact,
                    "tenant_address": tenant.tenant_address,
                    "tenant_city": tenant.tenant_city,
                    "tenant_country": tenant.tenant_country,
                    "tenant_postcode": tenant.tenant_postcode,
                    "tenant_GSTNo": tenant.tenant_GSTNo,
                    "tenant_PAN": tenant.tenant_PAN,
                    "tenant_status": tenant.tenant_status,
                    "tenant_plan_id": plan_info["tenant_plan_id"],
                    "tenant_plan_name": plan_info["tenant_plan_name"],
                    "from_date": plan_info["from_date"],
                    "end_date": plan_info["end_date"],
                    "payment_mode": plan_info["payment_mode"],
                    "del_flg": tenant.del_flg,
                    "created_at": tenant.created_at.isoformat()
                })

            logger.info(f"Retrieved {len(tenant_list)} tenants successfully")
            return jsonify({
                "data": tenant_list,
                "status": "success",
                "message": "All tenants retrieved successfully"
            }), 200

        except Exception as e:
            logger.error(f"Database query error: {str(e)}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": f"Failed to retrieve tenants: {str(e)}"
            }), 500

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Session initialization error: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": f"Internal server error: {str(e)}"
        }), 500

        

@tenant_blueprint.route("/<int:tenant_id>/update", methods=["PUT"])
@jwt_required()
def update_tenant_info(tenant_id):
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
            tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()

            if not tenant:
                return jsonify({
                    "data": {},
                    "message": "Tenant not found",
                    "status": "error"
                }), 404

            # Update the tenant's information with the provided data
            tenant.tenant_name = data.get("tenant_name", tenant.tenant_name)
            tenant.tenant_key = data.get("tenant_key", tenant.tenant_key)
            tenant.tenant_contact = data.get("tenant_contact", tenant.tenant_contact)
            tenant.tenant_address = data.get("tenant_address", tenant.tenant_address)
            tenant.tenant_city = data.get("tenant_city", tenant.tenant_city)
            tenant.tenant_country = data.get("tenant_country", tenant.tenant_country)
            tenant.tenant_postcode = data.get("tenant_postcode", tenant.tenant_postcode)
            tenant.tenant_GSTNo = data.get("tenant_GSTNo", tenant.tenant_GSTNo)
            tenant.tenant_PAN = data.get("tenant_PAN", tenant.tenant_PAN)
            tenant.tenant_status = data.get("tenant_status", tenant.tenant_status)
            tenant.del_flg = data.get("del_flg", tenant.del_flg)

            # Optional: if plan/payment payload is sent, also save into tbl_payment_info
            # This supports payload like:
            # { plan_name, plan_duration, plan_price, payment_status, ... }
            plan_name = data.get("plan_name")
            if plan_name:
                try:
                    plan_duration = int(data.get("plan_duration", 1))
                except (TypeError, ValueError):
                    plan_duration = 1

                try:
                    paid_amount = int(float(data.get("plan_price", 0)))
                except (TypeError, ValueError):
                    paid_amount = 0

                payment_status = data.get("payment_status", "pending")
                payment_mode = "Monthly" if plan_duration <= 1 else "Yearly"
                from_date = datetime.now()
                end_date = from_date + timedelta(days=plan_duration * 30)

                payment = tenant_payment_info(
                    razorpay_order_id=data.get("razorpay_order_id") or f"manual_order_{tenant_id}",
                    razorpay_payment_id=data.get("razorpay_payment_id") or f"manual_payment_{tenant_id}",
                    razorpay_signature=data.get("razorpay_signature"),
                    Paid_amount=paid_amount,
                    plans=plan_name,
                    payment_mode=payment_mode,
                    from_date=from_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                    tenant_id=tenant_id,
                    status=payment_status,
                    del_flg=False,
                )
                session.add(payment)

            session.commit()

            logger.info(f"Tenant {tenant_id} information updated successfully")
            return jsonify({
                "data": {
                    "tenant_id": tenant.tenant_id,
                    "plan_name": plan_name if plan_name else None
                },
                "message": "Tenant information updated successfully",
                "status": "success"
            }), 200

        except Exception as e:
            session.rollback()
            logger.error(f"Error updating tenant info: {str(e)}")
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

@tenant_blueprint.route("/<int:tenant_id>/status", methods=["PUT"])
@jwt_required()
def update_tenant_status(tenant_id):
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

        # Check if 'tenant_status' is in the request body
        if "tenant_status" not in data:
            return jsonify({
                "data": {},
                "message": "Missing tenant_status in request body",
                "status": "error"
            }), 400

        session = next(db_session())

        try:
            tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()

            if not tenant:
                return jsonify({
                    "data": {},
                    "message": "Tenant not found",
                    "status": "error"
                }), 404

            # Update the tenant status
            tenant.tenant_status = data["tenant_status"]

            session.commit()

            logger.info(f"Tenant {tenant_id} status updated to {tenant.tenant_status}")
            return jsonify({
                "data": {
                    "tenant_id": tenant.tenant_id,
                    "tenant_status": tenant.tenant_status
                },
                "message": "Tenant status updated successfully",
                "status": "success"
            }), 200

        except Exception as e:
            session.rollback()
            logger.error(f"Error updating tenant status: {str(e)}")
            return jsonify({
                "data": {},
                "message": f"An error occurred while updating tenant status: {str(e)}",
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


@tenant_blueprint.route("/<int:tenant_id>/notify-status", methods=["POST"])
@jwt_required()
def notify_tenant_status(tenant_id):
    try:
        claims = get_jwt()
        role = claims.get("role")
        if role != "superAdmin":
            logger.warning("Unauthorized notify-status attempt by role: %s", role)
            return jsonify({
                "data": {},
                "message": "Unauthorized: Super admin access required",
                "status": "error"
            }), 403

        data = request.json or {}
        tenant_status = data.get("tenant_status", "").strip()

        if not tenant_status:
            return jsonify({
                "data": {},
                "message": "Missing tenant_status in request body",
                "status": "error"
            }), 400

        session = next(db_session())
        try:
            tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                return jsonify({
                    "data": {},
                    "message": "Tenant not found",
                    "status": "error"
                }), 404

            if not tenant.tenant_emailid:
                return jsonify({
                    "data": {},
                    "message": "Tenant email not found",
                    "status": "error"
                }), 400

            _send_tenant_status_email(
                to_addr=tenant.tenant_emailid,
                tenant_name=tenant.tenant_name,
                tenant_status=tenant_status
            )

            logger.info(
                "Tenant status notification sent | tenant_id=%s email=%s status=%s",
                tenant_id,
                tenant.tenant_emailid,
                tenant_status
            )
            return jsonify({
                "data": {
                    "tenant_id": tenant.tenant_id,
                    "tenant_emailid": tenant.tenant_emailid,
                    "tenant_status": tenant_status
                },
                "message": "Tenant status notification sent successfully",
                "status": "success"
            }), 200
        finally:
            session.close()

    except Exception as e:
        logger.error("Failed to send tenant status notification: %s", str(e))
        return jsonify({
            "data": {},
            "message": f"Failed to send tenant status notification: {str(e)}",
            "status": "error"
        }), 500

# @tenant_blueprint.route("/<int:tenant_id>/plan", methods=["PUT"])
# @jwt_required()
# def update_tenant_plan(tenant_id):
#     try:
#         # Check superadmin role
#         claims = get_jwt()
#         role = claims.get("role")
#         if role != "superAdmin":
#             logger.warning(f"Unauthorized access attempt by user with role: {role}")
#             return jsonify({
#                 "data": {},
#                 "message": "Unauthorized: Super admin access required",
#                 "status": "error"
#             }), 403

#         data = request.json

#         # Check if 'plan_id' is in the request body
#         if "plan_id" not in data:
#             return jsonify({
#                 "data": {},
#                 "message": "Missing plan_id in request body",
#                 "status": "error"
#             }), 400

#         session = next(db_session())

#         try:
#             tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()

#             if not tenant:
#                 return jsonify({
#                     "data": {},
#                     "message": "Tenant not found",
#                     "status": "error"
#                 }), 404

#             plan_id = data["plan_id"]
#             plan = session.query(BotPlan).filter_by(plan_id=plan_id).first()

#             if not plan:
#                 return jsonify({
#                     "data": {},
#                     "message": "Invalid plan ID",
#                     "status": "error"
#                 }), 400

#             # Update the tenant's plan
#             tenant.tenant_plan_id = plan_id

#             session.commit()

#             logger.info(f"Tenant {tenant_id} plan updated to plan_id {plan_id}")
#             return jsonify({
#                 "data": {
#                     "tenant_id": tenant.tenant_id,
#                     "tenant_plan_id": tenant.tenant_plan_id
#                 },
#                 "message": "Tenant plan updated successfully",
#                 "status": "success"
#             }), 200

#         except Exception as e:
#             session.rollback()
#             logger.error(f"Error updating tenant plan: {str(e)}")
#             return jsonify({
#                 "data": {},
#                 "message": f"An error occurred while updating tenant plan: {str(e)}",
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



# @tenant_blueprint.route("/<int:tenant_id>/plan", methods=["PUT"])
# @jwt_required()
# def update_tenant_plan(tenant_id):
#     try:
#         # Check superadmin role
#         claims = get_jwt()
#         role = claims.get("role")
#         if role != "superAdmin":
#             logger.warning(f"Unauthorized access attempt by user with role: {role}")
#             return jsonify({
#                 "data": {},
#                 "message": "Unauthorized: Super admin access required",
#                 "status": "error"
#             }), 403

#         data = request.json

#         # Check if 'plan_id' is in the request body
#         if "plan_id" not in data:
#             return jsonify({
#                 "data": {},
#                 "message": "Missing plan_id in request body",
#                 "status": "error"
#             }), 400

#         session = next(db_session())

#         try:
#             tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()

#             if not tenant:
#                 return jsonify({
#                     "data": {},
#                     "message": "Tenant not found",
#                     "status": "error"
#                 }), 404

#             plan_id = data["plan_id"]
#             plan = session.query(BotPlan).filter_by(plan_id=plan_id, del_flg=False).first()

#             if not plan:
#                 return jsonify({
#                     "data": {},
#                     "message": "Invalid or deleted plan ID",
#                     "status": "error"
#                 }), 400

#             # Update the tenant's plan
#             tenant.tenant_plan_id = plan_id

#             # Insert a record into tenant_payment_info to treat as purchased
#             from_date = datetime.now()
#             end_date = from_date + timedelta(days=plan.plan_duration * 30)  # Approximate months to days
#             payment_mode = "Monthly" if plan.plan_duration <= 1 else "Yearly"
#             payment = tenant_payment_info(
#                 razorpay_order_id=None,
#                 razorpay_payment_id=None,
#                 razorpay_signature=None,
#                 Paid_amount=plan.plan_price,
#                 plans=plan.plan_name,
#                 payment_mode=payment_mode,
#                 from_date=from_date,
#                 end_date=end_date,
#                 tenant_id=tenant_id,
#                 status="success",
#                 del_flg=False
#             )
#             session.add(payment)
#             session.commit()

#             logger.info(f"Tenant {tenant_id} plan updated to plan_id {plan_id} and added to tenant_payment_info")
#             return jsonify({
#                 "data": {
#                     "tenant_id": tenant.tenant_id,
#                     "tenant_plan_id": tenant.tenant_plan_id,
#                     "tenant_plan_name": plan.plan_name,
#                     "from_date": from_date.strftime("%Y-%m-%d"),
#                     "end_date": end_date.strftime("%Y-%m-%d"),
#                     "payment_mode": payment_mode
#                 },
#                 "message": "Tenant plan updated successfully",
#                 "status": "success"
#             }), 200

#         except Exception as e:
#             session.rollback()
#             logger.error(f"Error updating tenant plan: {str(e)}")
#             return jsonify({
#                 "data": {},
#                 "message": f"An error occurred while updating tenant plan: {str(e)}",
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


@tenant_blueprint.route("/<int:tenant_id>/plan", methods=["PUT"])
@jwt_required()
def update_tenant_plan(tenant_id):
    try:
        # Check superadmin role
        claims = get_jwt()
        role = claims.get("role")
        logger.debug(f"JWT claims: {claims}")
        if role != "superAdmin":
            logger.warning(f"Unauthorized access attempt by user with role: {role}")
            return jsonify({
                "data": {},
                "message": "Unauthorized: Super admin access required",
                "status": "error"
            }), 403

        data = request.json
        logger.debug(f"Request body: {data}")

        # Check if 'plan_id' is in the request body
        if "plan_id" not in data:
            logger.error("Missing plan_id in request body")
            return jsonify({
                "data": {},
                "message": "Missing plan_id in request body",
                "status": "error"
            }), 400

        plan_id = data["plan_id"]
        logger.debug(f"Received plan_id: {plan_id}")

        session = next(db_session())

        try:
            tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                logger.error(f"Tenant not found for tenant_id: {tenant_id}")
                return jsonify({
                    "data": {},
                    "message": "Tenant not found",
                    "status": "error"
                }), 404

            # Check for active and non-deleted plan
            # plan = session.query(BotPlan).filter_by(plan_id=plan_id, del_flg=False || None, plan_status=True).first()
            plan = session.query(BotPlan).filter_by(plan_id=plan_id, plan_status=True).filter((BotPlan.del_flg == False) | (BotPlan.del_flg.is_(None))).first()
            if not plan:
                logger.error(f"No active plan found for plan_id: {plan_id} with del_flg=False and plan_status=True")
                return jsonify({
                    "data": {},
                    "message": "Invalid or inactive plan ID",
                    "status": "error"
                }), 400

            # Update the tenant's plan
            tenant.tenant_plan_id = plan_id

            # Insert a record into tenant_payment_info
            from_date = datetime.now()
            end_date = from_date + timedelta(days=plan.plan_duration * 30)  # Approximate months to days
            payment_mode = "Monthly" if plan.plan_duration <= 1 else "Yearly"
            payment = tenant_payment_info(
                razorpay_order_id="N/A",
                razorpay_payment_id="N/A",
                razorpay_signature="N/A",
                Paid_amount=plan.plan_price,
                plans=plan.plan_name,
                payment_mode=payment_mode,
                from_date=from_date,
                end_date=end_date,
                tenant_id=tenant_id,
                status="success",
                del_flg=False
            )
            session.add(payment)
            session.commit()

            logger.info(f"Tenant {tenant_id} plan updated to plan_id {plan_id} and added to tenant_payment_info")
            return jsonify({
                "data": {
                    "tenant_id": tenant.tenant_id,
                    "tenant_plan_id": tenant.tenant_plan_id,
                    "tenant_plan_name": plan.plan_name,
                    "from_date": from_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "payment_mode": payment_mode
                },
                "message": "Tenant plan updated successfully",
                "status": "success"
            }), 200

        except Exception as e:
            session.rollback()
            logger.error(f"Error updating tenant plan: {str(e)}")
            return jsonify({
                "data": {},
                "message": f"An error occurred while updating tenant plan: {str(e)}",
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


@tenant_blueprint.route("/delete/<int:tenant_id>", methods=["DELETE"])
@jwt_required()
def delete_tenant(tenant_id):
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
            tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                return jsonify({
                    "data": {},
                    "message": "Tenant not found",
                    "status": "error"
                }), 404

            # Perform soft delete by setting del_flg to True
            tenant.del_flg = True
            session.commit()

            logger.info(f"Tenant {tenant_id} soft deleted successfully")
            return jsonify({
                "data": {},
                "message": "Tenant soft deleted successfully",
                "status": "success"
            }), 200

        except Exception as e:
            session.rollback()
            logger.error(f"Error soft deleting tenant: {str(e)}")
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
