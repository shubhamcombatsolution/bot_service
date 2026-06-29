# billing_routes.py
import os
from flask import Flask, redirect, request, jsonify, Blueprint
from flask_jwt_extended import decode_token
from app.models import db, Tenant, tenant_payment_info
import logging
from razorpay import Client
from flask import Blueprint, render_template, request, jsonify, send_file
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import os
from datetime import datetime, timedelta
import json
from reportlab.platypus import Table, TableStyle
import subprocess
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, create_access_token
from io import BytesIO
from app.models import  TenantSubscription, BotPlan
from app.database.DatabaseOperationPostgreSQL import db_session
from app.utils import add_free_subscription
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

billing_info = Blueprint("billing_info", __name__)

razorpay_client = Client(auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET")))

def get_plan_description(plan):
    descriptions = {
        'simple': 'Essential Features for Startups and Individuals',
        'silver': 'Advanced Tools for Growing Teams',
        'golden': 'Complete Suite for Large Enterprises'
    }
    return descriptions.get(plan.lower(), 'Custom Plan')

def _build_invoice_pdf(company_name, company_address, client_name, client_email, plan_name, duration, transactions):
    if not transactions:
        raise ValueError("No transactions provided")

    first_tx = transactions[0]
    tx_date = first_tx.get("date", datetime.now().strftime("%d %b, %Y"))
    try:
        start_date = datetime.strptime(tx_date, "%d %b, %Y")
    except Exception:
        start_date = datetime.now()

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    default_logo_path = 'app/static/logo.png'
    if os.path.exists(default_logo_path):
        p.drawImage(default_logo_path, 50, height - 100, width=100, height=80)

    p.setFont("Helvetica-Bold", 16)
    p.drawString(160, height - 80, company_name)
    p.setFont("Helvetica", 12)
    p.drawString(160, height - 100, company_address)

    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 150, "Invoice")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 170, f"Invoice #: INV-{first_tx.get('id', 'N/A')}")
    p.drawString(50, height - 190, f"Date: {start_date.strftime('%d %b, %Y')}")
    p.drawString(50, height - 210, f"Due Date: {(start_date + timedelta(days=30)).strftime('%d %b, %Y')}")
    p.drawString(50, height - 230, "Payment Mode: Razorpay")
    p.drawString(50, height - 250, f"Client: {client_name} ({client_email})")

    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 290, "Plan Details")

    table_data = [
        ['Plan Name', 'Duration', 'Start Date', 'End Date', 'Amount'],
        [
            plan_name,
            duration,
            start_date.strftime('%d %b, %Y'),
            (start_date + timedelta(days=30)).strftime('%d %b, %Y'),
            f"${float(first_tx.get('amount', 0)):.2f}"
        ]
    ]
    table = Table(table_data, colWidths=[100, 100, 100, 100, 100])
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, '#000000'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('LEADING', (0, 0), (-1, -1), 12),
    ]))
    table.wrapOn(p, width, height)
    table.drawOn(p, 50, height - 340)

    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, height - 390, f"Total: ${sum(float(t.get('amount', 0)) for t in transactions):.2f}")
    p.setFont("Helvetica", 8)
    p.drawString(50, 50, "Thank you for your business!")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

def _get_billing_claims():
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return None, (jsonify({"error": "Authorization header missing or malformed"}), 401)

    jwt_token = auth_header.split(" ", 1)[1].strip()
    if not jwt_token:
        return None, (jsonify({"error": "Authorization token missing"}), 401)

    try:
        return decode_token(jwt_token), None
    except Exception as e:
        logger.warning(f"Invalid JWT in billing route: {e}")
        return None, (jsonify({"error": "Invalid authorization token"}), 401)

@billing_info.route('/billing-info', methods=['GET'])
def get_billing_info():
    claims, auth_error = _get_billing_claims()
    if auth_error:
        return auth_error

    tenant_id = claims.get("tenant_id")
    if not tenant_id:
        return jsonify({"error": "Tenant ID missing in token"}), 401

    try:
        # Fetch tenant payments
        payments = tenant_payment_info.query.filter_by(
            tenant_id=tenant_id
        ).order_by(tenant_payment_info.created_at.desc()).all()

        if not payments:
            return jsonify({'plan': None, 'invoices': []}), 200

        # Verify undecided payments (pending ones)
        for payment in payments:
            if payment.razorpay_payment_id and payment.status not in ['success', 'failed']:
                try:
                    payment_details = razorpay_client.payment.fetch(payment.razorpay_payment_id)
                    payment.status = 'success' if payment_details['status'] == 'captured' else 'failed'
                except Exception as e:
                    logger.error(f"Error verifying payment {payment.razorpay_payment_id}: {str(e)}")
                    payment.status = 'failed'

        db.session.commit()  # Commit once after updating all payments

        latest = payments[0]

        # Fetch active subscription
        existing = db.session.query(TenantSubscription).filter_by(
            tenant_id=tenant_id, subscription_status='active'
        ).first()

        plan_name = ""
        if existing:
            plan = db.session.query(BotPlan).filter(
                BotPlan.plan_id == existing.plan_id
            ).first()
            plan_name = plan.plan_name if plan else ""

        # Plan details
        plan_data = {
            'plan': plan_name,
            'type': latest.payment_mode.capitalize() if latest.payment_mode else None,
            'description': get_plan_description(latest.plans),
            'from_date': latest.from_date,
            'to_date': latest.end_date,
            'paid_amount': getattr(latest, "paid_amount", 0),  # safer than latest.Paid_amount
            'status': latest.status,
            "subscription_id" : existing.subscription_id
        }

        # Invoice details
        invoice_data = [{
            'number': f"Invoice-{p.intent_id}",
            'date': p.created_at.strftime('%d %b, %Y'),
            'amount': f"{getattr(p, 'paid_amount', 0):.2f}",
            'label': 'Paid' if p.status.lower() == 'success' else 'Declined',
            'color': 'badge-success' if p.status.lower() == 'success' else 'badge-danger'
        } for p in payments]

        return jsonify({
            'status': True,
            'plan': plan_data,
            'invoices': invoice_data
        }), 200

    except Exception as e:
        logger.error(f"Error fetching billing info: {str(e)}")
        return jsonify({'error': str(e)}), 500

@billing_info.route('/billing-info/<int:tenant_id>', methods=['GET'])
def get_billing_info_by_tenant(tenant_id):
    claims, auth_error = _get_billing_claims()
    if auth_error:
        return auth_error

    try:
        role = claims.get("role")

        # 🔒 Only admin access
        if role not in ["admin", "superAdmin"]:
            return jsonify({"error": "Unauthorized access"}), 403

        # ✅ Get tenant info
        tenant = Tenant.query.filter_by(tenant_id=tenant_id).first()

        # Fetch payments
        payments = tenant_payment_info.query.filter_by(
            tenant_id=tenant_id
        ).order_by(tenant_payment_info.created_at.desc()).all()

        if not payments:
            return jsonify({
                'plan': None,
                'invoices': [],
                'tenant_name': tenant.tenant_name if tenant else None
            }), 200

        # ✅ Verify payments
        for payment in payments:
            if payment.razorpay_payment_id and payment.status not in ['success', 'failed']:
                try:
                    payment_details = razorpay_client.payment.fetch(payment.razorpay_payment_id)
                    payment.status = 'success' if payment_details['status'] == 'captured' else 'failed'
                except Exception as e:
                    logger.error(f"Error verifying payment {payment.razorpay_payment_id}: {str(e)}")
                    payment.status = 'failed'

        db.session.commit()

        latest = payments[0]

        # ✅ Plan details (from latest payment only)
        plan_data = {
            'tenant_id': tenant_id,
            'tenant_name': tenant.tenant_name if tenant else None,
            'tenant_email': tenant.tenant_emailid if tenant else None,

            'plan': latest.plans,
            'type': latest.payment_mode.capitalize() if latest.payment_mode else None,
            'description': get_plan_description(latest.plans),

            'from_date': latest.from_date,
            'to_date': latest.end_date,

            # Safe amount
            'paid_amount': getattr(latest, "paid_amount", getattr(latest, "Paid_amount", 0)),

            'status': latest.status
        }

        # ✅ Invoice list
        invoice_data = [{
            'number': f"Invoice-{p.intent_id}",
            'date': p.created_at.strftime('%d %b, %Y'),
            'amount': f"{getattr(p, 'paid_amount', getattr(p, 'Paid_amount', 0)):.2f}",
            'status': p.status,
            'label': 'Paid' if p.status.lower() == 'success' else 'Declined',
            'color': 'badge-success' if p.status.lower() == 'success' else 'badge-danger'
        } for p in payments]

        return jsonify({
            'status': True,
            'plan': plan_data,
            'invoices': invoice_data
        }), 200

    except Exception as e:
        logger.error(f"Error fetching billing info by tenant: {str(e)}")
        return jsonify({'error': str(e)}), 500


@billing_info.route('/credits', methods=['GET'])
@jwt_required()
def get_credits():
    try:
        tenant_id = get_jwt_identity()

        subscription = db.session.query(TenantSubscription).filter_by(
            tenant_id=tenant_id,
            subscription_status='active',
            del_flg=False
        ).first()

        if not subscription:
            # Auto-assign free plan for tenants that slipped through registration
            subscription = add_free_subscription(db.session, tenant_id)
            if not subscription:
                return jsonify({
                    "status": False,
                    "message": "No active subscription found"
                }), 404
            db.session.commit()

        total_credits = subscription.total_plan_msg or 0
        remaining_credits = subscription.remaining_msg or 0

        used_credits = total_credits - remaining_credits

        return jsonify({
            "status": True,
            "used_credits": used_credits,
            "remaining_credits": remaining_credits
        }), 200

    except Exception as e:
        logger.error(f"Error fetching credits: {str(e)}")
        return jsonify({"error": str(e)}), 500


@billing_info.route('/plan-limits', methods=['GET'])
@jwt_required()
def get_plan_limits():
    try:
        tenant_id = get_jwt_identity()

        subscription = db.session.query(TenantSubscription).filter_by(
            tenant_id=tenant_id,
            subscription_status='active',
            del_flg=False
        ).first()

        if not subscription:
            subscription = add_free_subscription(db.session, tenant_id)
            if not subscription:
                return jsonify({"status": False, "message": "No active subscription"}), 404
            db.session.commit()

        plan = db.session.query(BotPlan).filter_by(plan_id=subscription.plan_id, del_flg=False).first()

        from app.models import CustomBotNew, Agent
        bot_count = db.session.query(CustomBotNew).filter_by(tenant_id=tenant_id, del_flg=False).count()
        agent_count = db.session.query(Agent).filter_by(tenant_id=tenant_id, del_flg=False).count()

        remaining_bots = int(subscription.remaining_bots or (plan.no_bot if plan else 1) or 1)
        remaining_agents = int(subscription.remaining_agent or (plan.no_agent if plan else 1) or 1)
        total_bots = int(plan.no_bot if plan else 1) or 1
        total_agents = int(plan.no_agent if plan else 1) or 1

        return jsonify({
            "status": True,
            "plan_name": plan.plan_name if plan else "Basic",
            "bots": {"used": bot_count, "allowed": total_bots, "remaining": max(0, total_bots - bot_count)},
            "agents": {"used": agent_count, "allowed": total_agents, "remaining": max(0, total_agents - agent_count)},
            "messages": {
                "used": (subscription.total_plan_msg or 0) - (subscription.remaining_msg or 0),
                "allowed": subscription.total_plan_msg or 0,
                "remaining": subscription.remaining_msg or 0,
            },
        }), 200

    except Exception as e:
        logger.error(f"Error fetching plan limits: {str(e)}")
        return jsonify({"error": str(e)}), 500


@billing_info.route('/all-invoices', methods=['GET'])
def get_all_invoices():
    claims, auth_error = _get_billing_claims()
    if auth_error:
        return auth_error

    try:
        role = claims.get("role")

        # 🔒 Restrict access
        if role not in ["admin", "superAdmin"]:
            return jsonify({"error": "Unauthorized access"}), 403

        # Fetch all payments
        payments = tenant_payment_info.query.order_by(
            tenant_payment_info.created_at.desc()
        ).all()

        if not payments:
            return jsonify({'invoices': []}), 200

        # Verify pending payments
        for payment in payments:
            if payment.razorpay_payment_id and payment.status not in ['success', 'failed']:
                try:
                    payment_details = razorpay_client.payment.fetch(payment.razorpay_payment_id)
                    payment.status = 'success' if payment_details['status'] == 'captured' else 'failed'
                except Exception as e:
                    logger.error(f"Error verifying payment {payment.razorpay_payment_id}: {str(e)}")
                    payment.status = 'failed'

        db.session.commit()

        # Return FULL DATA
        invoice_data = []
        for p in payments:
            invoice_data.append({
                "intent_id": p.intent_id,

                # ✅ Tenant Info (NEW)
                "tenant_id": p.tenant_id,
                "tenant_name": p.tenant.tenant_name if p.tenant else None,

                # Plan
                "plan": p.plans,
                "payment_mode": p.payment_mode,

                # Dates
                "from_date": p.from_date,
                "end_date": p.end_date,
                "created_at": p.created_at.strftime('%d %b, %Y %H:%M'),

                # Amount
                "amount": p.Paid_amount,

                # Status
                "status": "Paid" if p.status.lower() == "success" else "Declined",
            })
        return jsonify({
            "status": True,
            "count": len(invoice_data),
            "invoices": invoice_data
        }), 200

    except Exception as e:
        logger.error(f"Error fetching all invoices: {str(e)}")
        return jsonify({"error": str(e)}), 500      

@billing_info.route('/generate-invoice', methods=['GET', 'POST'])
def generate_invoice():
    claims, auth_error = _get_billing_claims()
    if auth_error:
        return auth_error

    tenant_id = claims.get("tenant_id")
    if not tenant_id:
        return jsonify({"error": "Tenant ID missing in token"}), 401

    tenant_data= Tenant.query.filter_by(tenant_id=tenant_id).order_by(Tenant.tenant_id.desc()).first()

    if request.method == 'POST':
        logger.info(f"Received headers: {request.headers}")
        logger.info(f"Received data: {request.get_data(as_text=True)}")

        # Get JSON data from frontend
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided. Content-Type must be 'application/json'."}), 400
        company_name = data.get('company_name')
        company_address = data.get('company_address')
        client_name =tenant_data.tenant_name
        client_email =tenant_data.tenant_emailid
        plan_name = data.get('plan_name', 'Standard Plan')
        duration = data.get('duration', 'Monthly')
        transactions_json = data.get('transactions')


    if request.method == 'POST':
        logger.info(f"Received headers: {request.headers}")
        logger.info(f"Received data: {request.get_data(as_text=True)}")

        # Get JSON data from frontend
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided. Content-Type must be 'application/json'."}), 400

        company_name = data.get('company_name', 'MyCompany')
        company_address = data.get('company_address', '123 Main St, Mumbai, India')
        client_name = data.get('client_name', 'John Doe')
        client_email = data.get('client_email', 'john.doe@example.com')  # From JWT or frontend
        plan_name = data.get('plan_name', 'Standard Plan')
        duration = data.get('duration', 'Monthly')
        transactions_json = data.get('transactions')

        # Handle transactions
        try:
            transactions = json.loads(transactions_json) if transactions_json else []
            if not isinstance(transactions, list):
                raise ValueError("Transactions must be a list")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Invalid JSON format for transactions: {e}")
            return jsonify({"error": f"Invalid JSON format for transactions: {str(e)}"}), 400

        # Use a default logo
        default_logo_path = 'app/static/logo.png'
        if not os.path.exists(default_logo_path):
            logger.error(f"Default logo not found at {default_logo_path}")
            return jsonify({"error": "Default logo not found."}), 400

        logo = ImageReader(default_logo_path)

        # Generate PDF
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # Add logo and company details
        p.drawImage(default_logo_path, 50, height - 100, width=100, height=80)
        p.setFont("Helvetica-Bold", 16)
        p.drawString(160, height - 80, company_name)
        p.setFont("Helvetica", 12)
        p.drawString(160, height - 100, company_address)

        # Add invoice metadata
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, height - 150, "Invoice")
        p.setFont("Helvetica", 10)
        p.drawString(50, height - 170, f"Invoice #: INV-{transactions[0].get('id', 'N/A')}")
        p.drawString(50, height - 190, f"Date: {datetime.now().strftime('%d %b, %Y')}")
        p.drawString(50, height - 210, f"Due Date: {(datetime.now() + timedelta(days=30)).strftime('%d %b, %Y')}")
        p.drawString(50, height - 230, "Payment Mode: Razorpay")
        p.drawString(50, height - 250, f"Payment ID: {transactions[0].get('id', 'N/A')}")
        p.drawString(50, height - 270, f"Client: {client_name} ({client_email})")
        p.drawString(50, height - 290, "Support: support@mycompany.com")

        # Add plan details header
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, height - 320, "Plan Details")

        # Add plan details table
        y = height - 350
        data = [
            ['Plan Name', 'Duration', 'Start Date', 'End Date', 'Amount'],
            [plan_name, duration, datetime.strptime(transactions[0].get('date', '24 Jun, 2025'), '%d %b, %Y').strftime('%d %b, %Y'),
             (datetime.strptime(transactions[0].get('date', '24 Jun, 2025'), '%d %b, %Y') + timedelta(days=30)).strftime('%d %b, %Y'),
             f"${float(transactions[0].get('amount', '0')):.2f}"]
        ]
        table = Table(data, colWidths=[100, 100, 100, 100, 100])
        table.setStyle(TableStyle([
            ('TEXTCOLOR', (0, 0), (-1, -1), '#000000'),  # Black text
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, 1), 10),
            ('GRID', (0, 0), (-1, -1), 1, '#000000'),  # Black grid
            ('LEADING', (0, 0), (-1, -1), 12),
        ]))
        table.wrapOn(p, width, height)
        table.drawOn(p, 50, y - 30)  # Adjust y position based on table height
        y -= table._height + 20

        # Add total
        p.setFont("Helvetica-Bold", 10)
        p.drawString(450, y, f"Total: ${sum(float(t.get('amount', 0)) for t in transactions):.2f}")
        y -= 20

        # Add Terms and Conditions
        p.setFont("Helvetica-Bold", 10)
        p.drawString(50, y, "Terms and Conditions:-")
        p.setFont("Helvetica", 9)
        terms_y = y - 15
        terms_lines = [
            "1.Payment is non-refundable.",
            "2.Plan valid till end date.",
            "3.Auto-renews unless canceled.",
            "4.For issues, contact support@mycompany.com within 7 days."
        ]
        for line in terms_lines:
            p.drawString(50, terms_y, line)
            terms_y -= 12  # Adjust vertical spacing (12pt per line)
        # Ensure minimum y to avoid overlap with footer
        if terms_y < 50:
            p.showPage()
            terms_y = height - 100

        p.setFont("Helvetica", 8)
        p.drawString(50, 50, "Thank you for your business!")

        p.showPage()
        p.save()
        buffer.seek(0)

        return send_file(buffer, as_attachment=True, download_name=f"invoice_{transactions[0]['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", mimetype='application/pdf')

    return render_template('invoice_form.html')
    
@billing_info.route('/generate-invoice/<int:tenant_id>', methods=['POST'])
def generate_invoices(tenant_id):
    try:
        session = next(db_session())

        tenant_data = (
            session.query(Tenant)
            .filter_by(tenant_id=tenant_id)
            .first()
        )

        if not tenant_data:
            return jsonify({"error": "Tenant not found"}), 404

        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        company_name = data.get('company_name', 'MyCompany')
        company_address = data.get('company_address', 'India')

        client_name = tenant_data.tenant_name
        client_email = tenant_data.tenant_emailid

        plan_name = data.get('plan_name', 'Standard Plan')
        duration = data.get('duration', 'Monthly')
        transactions_json = data.get('transactions')

        # ✅ Parse transactions
        try:
            transactions = json.loads(transactions_json) if transactions_json else []
            if not isinstance(transactions, list):
                raise ValueError("Transactions must be a list")
        except Exception as e:
            return jsonify({"error": str(e)}), 400

        if not transactions:
            return jsonify({"error": "No transactions provided"}), 400

        buffer = _build_invoice_pdf(
            company_name=company_name,
            company_address=company_address,
            client_name=client_name,
            client_email=client_email,
            plan_name=plan_name,
            duration=duration,
            transactions=transactions,
        )

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"invoice_{transactions[0]['id']}.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        logger.exception("generate_invoice error")
        return jsonify({"error": str(e)}), 500
