import os
from flask import Flask, redirect, request, jsonify, Blueprint
from flask_jwt_extended import JWTManager, get_jwt_identity, jwt_required, get_jwt
from app.models import db, Tenant, tenant_payment_info, BotPlan
from app.database.DatabaseOperationPostgreSQL import db_session
import hmac
import hashlib
from datetime import datetime, timedelta
from razorpay import Client
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define Blueprint
plans_subscription = Blueprint("plans", __name__)

# Razorpay Client verification
razorpay_client = Client(auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET")))

@plans_subscription.route("/create-order", methods=["POST"])
@jwt_required()
def create_order():
    try:
        data = request.get_json()
        tenant_id = get_jwt_identity()
        amount = data.get("amount")  # Amount in paise
        plan_name = data.get("plan_name")
        payment_mode = data.get("payment_mode")  # Monthly/Yearly

        if not all([tenant_id, amount, plan_name, payment_mode]):
            return jsonify({"error": "Amount, plan_name, and payment_mode are required"}), 400

        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            return jsonify({"error": "Tenant not found"}), 404

        order = razorpay_client.order.create({
            "amount": int(amount),
            "currency": "INR",
            "payment_capture": 1
        })

        return jsonify({
            "order_id": order['id'],
            "amount": order['amount'],
            "currency": order['currency'],
            "plan_name": plan_name,
            "payment_mode": payment_mode
        })

    except Exception as e:
        logger.error(f"Error creating order: {str(e)}")
        return jsonify({"error": str(e)}), 500

processed_payments = set()

# @plans_subscription.route("/verify-payment", methods=["POST"])
# @jwt_required()
# def verify_payment():
#     try:
#         data = request.get_json()
#         tenant_id = get_jwt_identity()
#         razorpay_order_id = data.get("razorpay_order_id")
#         razorpay_payment_id = data.get("razorpay_payment_id")
#         razorpay_signature = data.get("razorpay_signature")
#         paid_amount = data.get("Paid_amount")  # Amount in rupees
#         plan_name = data.get("plans")
#         payment_mode = data.get("payment_mode")
#         from_date = data.get("from_date")
#         end_date = data.get("end_date")

#         if not all([razorpay_order_id, razorpay_payment_id, paid_amount, plan_name, payment_mode, from_date, end_date]):
#             return jsonify({"status": "failed", "message": "Missing required fields."}), 400

#         if razorpay_payment_id in processed_payments:
#             return jsonify({"status": "already_processed", "message": "This payment has already been verified."}), 409

#         tenant = db.session.get(Tenant, tenant_id)
#         if not tenant:
#             return jsonify({"status": "failed", "message": "Tenant not found."}), 404

#         # Verify payment with Razorpay
#         payment_details = razorpay_client.payment.fetch(razorpay_payment_id)
#         status = 'success' if payment_details['status'] == 'captured' else 'failed'

#         # Signature verification (skip if signature is not provided)
#         if razorpay_signature:
#             generated_signature = hmac.new(
#                 key=bytes(os.getenv("RAZORPAY_KEY_SECRET"), 'utf-8'),
#                 msg=bytes(razorpay_order_id + "|" + razorpay_payment_id, 'utf-8'),
#                 digestmod=hashlib.sha256
#             ).hexdigest()
#             is_valid_signature = generated_signature == razorpay_signature
#         else:
#             is_valid_signature = False

#         # Find the corresponding BotPlan by plan_name
#         plan = db.session.query(BotPlan).filter_by(plan_name=plan_name, plan_status=True, del_flg=False).first()
#         if not plan:
#             return jsonify({"status": "failed", "message": "Plan not found or inactive."}), 400

#         # Save payment record
#         payment = tenant_payment_info(
#             razorpay_order_id=razorpay_order_id,
#             razorpay_payment_id=razorpay_payment_id,
#             razorpay_signature=razorpay_signature or None,
#             Paid_amount=paid_amount,
#             plans=plan_name,
#             payment_mode=payment_mode,
#             from_date=from_date,
#             end_date=end_date,
#             tenant_id=tenant_id,
#             status=status if is_valid_signature or status == 'failed' else 'failed'
#         )
#         db.session.add(payment)

#         # Update tenant's plan_id if payment is successful
#         if is_valid_signature and status == 'success':
#             tenant.tenant_plan_id = plan.plan_id
#             processed_payments.add(razorpay_payment_id)

#         db.session.commit()

#         if is_valid_signature and status == 'success':
#             return jsonify({"status": "success", "message": "Payment verified successfully."})
#         else:
#             return jsonify({"status": "failed", "message": "Payment verification failed."}), 400

#     except Exception as e:
#         db.session.rollback()
#         logger.error(f"Payment verification failed: {str(e)}")
#         return jsonify({"status": "failed", "message": str(e)}), 500

@plans_subscription.route("/verify-payment", methods=["POST"])
@jwt_required()
def verify_payment():
    try:
        data = request.get_json()
        tenant_id = get_jwt_identity()
        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")
        paid_amount = data.get("Paid_amount")  # Amount in rupees
        plan_name = data.get("plans")
        payment_mode = data.get("payment_mode")
        from_date = data.get("from_date")
        end_date = data.get("end_date")

        if not all([razorpay_order_id, razorpay_payment_id, paid_amount, plan_name, payment_mode, from_date, end_date]):
            return jsonify({"status": "failed", "message": "Missing required fields."}), 400

        if razorpay_payment_id in processed_payments:
            return jsonify({"status": "already_processed", "message": "This payment has already been verified."}), 409

        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            return jsonify({"status": "failed", "message": "Tenant not found."}), 404

        # Verify payment with Razorpay
        payment_details = razorpay_client.payment.fetch(razorpay_payment_id)
        status = 'success' if payment_details['status'] == 'captured' else 'failed'

        # Signature verification (skip if signature is not provided)
        if razorpay_signature:
            generated_signature = hmac.new(
                key=bytes(os.getenv("RAZORPAY_KEY_SECRET"), 'utf-8'),
                msg=bytes(razorpay_order_id + "|" + razorpay_payment_id, 'utf-8'),
                digestmod=hashlib.sha256
            ).hexdigest()
            is_valid_signature = generated_signature == razorpay_signature
        else:
            is_valid_signature = False

        #  **Deactivate any previous “current” payment rows for tenant**
        (
            db.session.query(tenant_payment_info)
            .filter_by(tenant_id=tenant_id, del_flg=False)   # or is_active=True
            .update({"del_flg": True}, synchronize_session="fetch")
        )
        # Save payment record
        payment = tenant_payment_info(
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature or None,  # Handle nullable signature
            Paid_amount=paid_amount,
            plans=plan_name,
            payment_mode=payment_mode,
            from_date=from_date,
            end_date=end_date,
            tenant_id=tenant_id,
            del_flg = False,
            status=status if is_valid_signature or status == 'failed' else 'failed'
        )
        db.session.add(payment)
        db.session.commit()

        if is_valid_signature and status == 'success':
            processed_payments.add(razorpay_payment_id)
            return jsonify({"status": "success", "message": "Payment verified successfully."})
        else:
            return jsonify({"status": "failed", "message": "Payment verification failed."}), 400

    except Exception as e:
        logger.error(f"Payment verification failed: {str(e)}")
        return jsonify({"status": "failed", "message": str(e)}), 500


@plans_subscription.route("/check-payment-status", methods=["GET"])
@jwt_required()
def check_payment_status():
    try:
        tenant_id = get_jwt_identity()
        order_id = request.args.get('order_id')
        plan_name = request.args.get('plan_name')
        payment_mode = request.args.get('payment_mode')

        # Validate required parameters
        if not order_id:
            return jsonify({"status": "failed", "message": "Order ID is required"}), 400
        if not all([plan_name, payment_mode]):
            return jsonify({"status": "failed", "message": "plan_name and payment_mode are required"}), 400

        # Validate tenant
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            return jsonify({"status": "failed", "message": "Tenant not found"}), 404

        # Fetch order payments from Razorpay
        try:
            order_payments = razorpay_client.order.payments(order_id)
        except Exception as e:
            logger.error(f"Razorpay order fetch failed for order {order_id}: {str(e)}")
            return jsonify({"status": "failed", "message": "Invalid order ID or Razorpay error"}), 400

        payment_statuses = []
        updated = False

        # Current date and time
        current_datetime = datetime.now()

        for payment in order_payments.get('items', []):
            payment_id = payment.get('id')
            if not payment_id:
                continue

            try:
                # Fetch detailed payment status
                payment_details = razorpay_client.payment.fetch(payment_id)
                status = payment_details.get('status', 'failed')

                # Check if payment already exists
                existing_payment = tenant_payment_info.query.filter_by(razorpay_payment_id=payment_id).first()
                from_date = current_datetime.strftime("%Y-%m-%d")
                end_date = (current_datetime + timedelta(days=365 if payment_mode == "Yearly" else 30)).strftime("%Y-%m-%d")

                if not existing_payment:
                    new_payment = tenant_payment_info(
                        razorpay_order_id=order_id,
                        razorpay_payment_id=payment_id,
                        razorpay_signature=None,
                        Paid_amount=payment.get('amount') / 100,
                        plans=plan_name,
                        payment_mode=payment_mode,
                        from_date=from_date,
                        end_date=end_date,
                        tenant_id=tenant_id,
                        status=status
                    )
                    db.session.add(new_payment)
                    # Update tenant_plan_id if payment is successful
                    plan = db.session.query(BotPlan).filter_by(plan_name=plan_name, plan_status=True, del_flg=False).first()
                    if plan and status == 'success':
                        tenant.tenant_plan_id = plan.plan_id
                    updated = True
                elif existing_payment.status != status:
                    existing_payment.status = status
                    db.session.add(existing_payment)
                    # Update tenant_plan_id if payment is successful
                    plan = db.session.query(BotPlan).filter_by(plan_name=plan_name, plan_status=True, del_flg=False).first()
                    if plan and status == 'success':
                        tenant.tenant_plan_id = plan.plan_id
                    updated = True

                payment_statuses.append({
                    "payment_id": payment_id,
                    "status": status,
                    "amount": payment.get('amount') / 100
                })

            except Exception as e:
                logger.error(f"Razorpay payment fetch failed for payment {payment_id}: {str(e)}")
                payment_statuses.append({
                    "payment_id": payment_id,
                    "status": "failed",
                    "amount": payment.get('amount') / 100,
                    "error": str(e)
                })

        if updated:
            db.session.commit()

        if not payment_statuses:
            return jsonify({"status": "failed", "message": "No payments found for this order"}), 404

        return jsonify({
            "status": "success",
            "message": "Payment statuses updated",
            "payment_statuses": payment_statuses
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error checking payment status for order {order_id}: {str(e)}")
        return jsonify({"status": "failed", "message": str(e)}), 500
    
@plans_subscription.route("/get_tenant_plan", methods=["GET"])
@jwt_required()
def get_tenant_plan():
    try:
        tenant_id = get_jwt_identity()

        all_plans = (
            db.session.query(tenant_payment_info)
            .filter_by(tenant_id=tenant_id, del_flg=False)
            .order_by(tenant_payment_info.created_at.desc())
            .all()
        )

        if not all_plans:
            return jsonify({"status": "no_plan", "message": "No plan purchased."}), 200

        updated = False
        active_plans = []
        today = datetime.now().date()

        for plan in all_plans:
            try:
                end_date = datetime.strptime(plan.end_date, "%Y-%m-%d").date() if isinstance(plan.end_date, str) else plan.end_date.date()
                if plan.status == "success" and end_date < today:
                    plan.status = "failed"
                    updated = True
                elif plan.status == "success":
                    active_plans.append(plan)
            except Exception as e:
                logger.error(f"Invalid end_date format: {plan.end_date} - {e}")
                continue

        if updated:
            db.session.commit()

        if not active_plans:
            return jsonify({"status": "expired", "message": "All plans have expired."}), 200

        plans_data = []
        for plan in active_plans:
            from_date = plan.from_date.strftime("%Y-%m-%d") if isinstance(plan.from_date, datetime) else str(plan.from_date)
            end_date = plan.end_date.strftime("%Y-%m-%d") if isinstance(plan.end_date, datetime) else str(plan.end_date)
            plans_data.append({
                "plan_name": plan.plans,
                "payment_mode": plan.payment_mode,
                "from_date": from_date,
                "end_date": end_date,
                "status": plan.status
            })

        return jsonify({"status": "success", "data": plans_data}), 200

    except Exception as e:
        logger.error(f"Error fetching tenant plan: {str(e)}")
        return jsonify({"status": "failed", "message": str(e)}), 500


# @plans_subscription.route("/get_tenant_plan", methods=["POST"])
# @jwt_required()
# def get_tenant_plan():
#     try:
#         tenant_id = get_jwt_identity()

#         session = next(db_session())
#         try:
#             # Fetch payment plans from tenant_payment_info
#             payment_plans = (
#                 session.query(tenant_payment_info)
#                 .filter_by(tenant_id=tenant_id, del_flg=False)
#                 .order_by(tenant_payment_info.created_at.desc())
#                 .all()
#             )

#             # Fetch tenant's assigned plan from Tenant table
#             tenant = session.query(Tenant).filter_by(tenant_id=tenant_id, del_flg=False).first()
#             assigned_plan = None
#             if tenant and tenant.tenant_plan_id:
#                 plan = session.query(BotPlan).filter_by(plan_id=tenant.tenant_plan_id, del_flg=False).first()
#                 if plan:
#                     from_date = datetime.now()
#                     end_date = from_date + timedelta(days=plan.plan_duration * 30)
#                     assigned_plan = {
#                         "plan_name": plan.plan_name,
#                         "payment_mode": "Monthly" if plan.plan_duration <= 1 else "Yearly",
#                         "from_date": from_date.strftime("%Y-%m-%d"),
#                         "end_date": end_date.strftime("%Y-%m-%d"),
#                         "status": "success"
#                     }

#             today = datetime.now().date()
#             active_plans = []
#             updated = False

#             # Process payment plans
#             for plan in payment_plans:
#                 try:
#                     end_date = datetime.strptime(plan.end_date, "%Y-%m-%d").date() if isinstance(plan.end_date, str) else plan.end_date.date()
#                     if plan.status == "success" and end_date < today:
#                         plan.status = "failed"
#                         updated = True
#                     elif plan.status == "success":
#                         active_plans.append({
#                             "plan_name": plan.plans,
#                             "payment_mode": plan.payment_mode,
#                             "from_date": plan.from_date.strftime("%Y-%m-%d") if isinstance(plan.from_date, datetime) else str(plan.from_date),
#                             "end_date": plan.end_date.strftime("%Y-%m-%d") if isinstance(plan.end_date, datetime) else str(plan.end_date),
#                             "status": plan.status
#                         })
#                 except Exception as e:
#                     logger.error(f"Invalid end_date format: {plan.end_date} - {e}")
#                     continue

#             # Add assigned plan if it exists and isn't duplicated
#             if assigned_plan:
#                 # Check if assigned plan is already in payment plans
#                 if not any(p["plan_name"] == assigned_plan["plan_name"] and p["end_date"] == assigned_plan["end_date"] for p in active_plans):
#                     active_plans.append(assigned_plan)

#             if updated:
#                 session.commit()

#             if not active_plans:
#                 return jsonify({"status": "expired", "message": "All plans have expired."}), 200

#             return jsonify({"status": "success", "data": active_plans}), 200

#         except Exception as e:
#             logger.error(f"Error fetching tenant plan: {str(e)}")
#             return jsonify({"status": "failed", "message": str(e)}), 500

#         finally:
#             session.close()

#     except Exception as e:
#         logger.error(f"Error initializing session: {str(e)}")
#         return jsonify({"status": "failed", "message": str(e)}), 500