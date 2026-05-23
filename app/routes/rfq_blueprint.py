from flask import Blueprint, request, jsonify
from datetime import datetime
import uuid
from app.models import RfqMaterialDetails
from app.database.DatabaseOperationPostgreSQL import db_session
from app.models import SupplierQuotations  # For future linking

rfq_blueprint = Blueprint("rfq", __name__)


def generate_rfq_no(session):
    year = datetime.utcnow().year

    # Find highest RFQ for this year
    last_rfq = (
        session.query(RfqMaterialDetails)
        .filter(RfqMaterialDetails.rfq_no.like(f"RFQ_{year}_%"))
        .order_by(RfqMaterialDetails.rfq_no.desc())
        .first()
    )

    if last_rfq:
        # Extract last number
        last_number = int(last_rfq.rfq_no.split("_")[-1])
        new_number = last_number + 1
    else:
        new_number = 1

    # Format number as 001, 002, 003
    formatted_number = str(new_number).zfill(3)

    return f"RFQ_{year}_{formatted_number}"

    
@rfq_blueprint.route("/add", methods=["POST"])
def add_rfq_material_details():
    session = next(db_session())
    try:
        payload = request.get_json() or {}
        print(f"Incoming RFQ payload: {payload}")

        # ✅ Validate required fields...
        
        # ✅ Generate RFQ number with format RFQ_YYYY_001
        rfq_no = generate_rfq_no(session)

        new_rfq = RfqMaterialDetails(
            rfq_no=rfq_no,
            requested_by=payload.get("requested_by"),
            user_email=payload.get("user_email"),
            material_description=payload.get("material_description"),
            uom=payload.get("uom"),
            make_preferred=payload.get("make_preferred"),
            notes=payload.get("notes"),
            total_required_quantity=payload.get("total_required_quantity"),
            required_delivery_date=payload.get("required_delivery_date"),
            lead_time_required_days=payload.get("lead_time_required_days"),
            req_received_date=datetime.utcnow().date()
        )

        session.add(new_rfq)
        session.commit()

        return jsonify({
            "status": True,
            "status_code": 201,
            "message": "RFQ added successfully",
            "rfq_no": rfq_no
        }), 201

    except Exception as e:   # ✅ ADD THIS
        session.rollback()
        print("Error while adding RFQ:", e)
        return jsonify({
            "status": False,
            "status_code": 500,
            "error": str(e),
            "message": "Error while adding RFQ"
        }), 500

    finally:                # ✅ ADD THIS
        session.close()

# ✅ 2. Update RFQ Material Details (PUT)
@rfq_blueprint.route("/update", methods=["POST"])
def update_rfq_material_details():
    session = next(db_session())
    try:
        payload = request.get_json() or {}
        rfq_no = payload.get("rfq_no")

        if not rfq_no:
            return jsonify({
                "status": False,
                "status_code": 400,
                "message": "Missing 'rfq_no'"
            }), 400

        rfq_record = session.query(RfqMaterialDetails).filter_by(rfq_no=rfq_no).first()

        if not rfq_record:
            return jsonify({
                "status": False,
                "status_code": 404,
                "message": f"RFQ not found: {rfq_no}"
            }), 404

        # ✅ Update new model fields only
        update_fields = [
            "requested_by", "user_email", "material_description", "uom",
            "make_preferred", "notes", "total_required_quantity",
            "required_delivery_date", "lead_time_required_days"
        ]

        for key in update_fields:
            if key in payload:
                setattr(rfq_record, key, payload[key])

        rfq_record.updated_at = datetime.utcnow()

        session.commit()

        return jsonify({
            "status": True,
            "status_code": 200,
            "message": f"RFQ updated successfully for {rfq_no}"
        }), 200

    except Exception as e:
        session.rollback()
        print("Error while updating RFQ:", e)
        return jsonify({
            "status": False,
            "status_code": 500,
            "error": str(e),
            "message": "Error updating RFQ"
        }), 500
    finally:
        session.close()



# ✅ 3. Fetch RFQ Details (GET)
@rfq_blueprint.route("/<string:rfq_no>", methods=["GET"])
def get_rfq_material_details(rfq_no):
    session = next(db_session())
    try:
        rfq = session.query(RfqMaterialDetails).filter_by(rfq_no=rfq_no).first()

        if not rfq:
            return jsonify({
                "status": False,
                "status_code": 404,
                "message": f"RFQ not found: {rfq_no}"
            }), 404

        data = {
            "rfq_no": rfq.rfq_no,
            "requested_by": rfq.requested_by,
            "user_email": rfq.user_email,
            "material_description": rfq.material_description,
            "uom": rfq.uom,
            "make_preferred": rfq.make_preferred,
            "notes": rfq.notes,
            "total_required_quantity": str(rfq.total_required_quantity),
            "required_delivery_date": str(rfq.required_delivery_date),
            "lead_time_required_days": rfq.lead_time_required_days,
            "status": rfq.status,
            "req_received_date": str(rfq.req_received_date),
            "created_at": rfq.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": rfq.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

        return jsonify({
            "status": True,
            "status_code": 200,
            "message": "RFQ details fetched successfully",
            "data": data
        }), 200

    except Exception as e:
        print("Error while fetching RFQ:", e)
        return jsonify({
            "status": False,
            "status_code": 500,
            "error": str(e),
            "message": "Error while fetching RFQ"
        }), 500
    finally:
        session.close()


@rfq_blueprint.route("/fetch", methods=["POST"])
def fetch_quotations():
    session = next(db_session())
    try:
        data = request.get_json()
        rfq_no = data.get("rfq_no")

        if not rfq_no:
            return jsonify({
                "status": False,
                "status_code": 400,
                "message": "Missing 'rfq_no' in request payload"
            }), 400

        print(f"🔍 Fetching quotations for RFQ: {rfq_no}")

        # ✅ Fetch RFQ details
        rfq = session.query(RfqMaterialDetails).filter_by(rfq_no=rfq_no).first()
        if not rfq:
            return jsonify({
                "status": False,
                "status_code": 404,
                "message": f"RFQ not found: {rfq_no}"
            }), 404

        rfq_data = {
            "rfq_no": rfq.rfq_no,
            "requested_by": rfq.requested_by,
            "user_email": rfq.user_email,
            "material_description": rfq.material_description,
            "uom": rfq.uom,
            "make_preferred": rfq.make_preferred,
            "notes": rfq.notes,
            "total_required_quantity": str(rfq.total_required_quantity),
            "required_delivery_date": str(rfq.required_delivery_date),
            "lead_time_required_days": rfq.lead_time_required_days,
            "status": rfq.status,
            "req_received_date": str(rfq.req_received_date)
        }

        # ✅ Fetch supplier quotations
        supplier_quotations = session.query(SupplierQuotations).filter_by(rfq_no=rfq_no).all()

        quotation_list = [
            {
                "id": q.id,
                "rfq_no": q.rfq_no,
                "supplier_email": q.supplier_email,
                "supplier_name": q.supplier_name,
                "quotation_file_path": q.quotation_file_path,
                "lead_time_days": q.lead_time_days,
                "offered_quantity": q.offered_quantity,
                "unit_price": str(q.unit_price) if q.unit_price is not None else None,
                "currency": q.currency,
                "status": q.status,
                "evaluation_reason": q.evaluation_reason,
                "notified": q.notified,
                "remarks": q.remarks,
                # "last_updated": q.last_updated.strftime("%Y-%m-%d %H:%M:%S") if q.last_updated else None
                "margin": q.margin,
                "margin_amount" : q.margin_amount,
                "total_amount" : q.total_amount,
                "final_amount" : q.final_amount
            }
            for q in supplier_quotations
        ]

        return jsonify({
            "status": True,
            "status_code": 200,
            "message": "Supplier quotations retrieved successfully",
            "rfq_data": rfq_data,
            "supplier_list": quotation_list
        }), 200

    except Exception as e:
        print("❌ Error in fetch_quotations:", e)
        return jsonify({
            "status": False,
            "status_code": 500,
            "message": "Error while fetching supplier quotations",
            "error": str(e)
        }), 500

    finally:
        session.close()
