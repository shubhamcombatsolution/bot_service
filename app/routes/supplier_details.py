from flask import Blueprint, request, jsonify
from sqlalchemy import or_
from sqlalchemy.orm import load_only
from collections import defaultdict
from app.models import SupplierDetails
from app.database.DatabaseOperationPostgreSQL import db_session
from sqlalchemy import func
from sqlalchemy import String

suppliers_blueprint = Blueprint("suppliers", __name__)

@suppliers_blueprint.route("/search", methods=["POST"])
# @jwt_required(optional=True)
def search_supplier_by_description():
    try:
        payload = request.get_json() or {}
        print(f"Incoming payload: {payload}")

        # ✅ Handle fetch_all request to get all material descriptions
        if payload.get("fetch_all", False):
            session = next(db_session())
            try:
                materials = (
                    session.query(SupplierDetails.material_description)
                    .filter(SupplierDetails.active_flag == True)
                    .distinct()
                    .order_by(SupplierDetails.material_description.asc())
                    .all()
                )
                material_list = [m[0] for m in materials if m[0]]
            finally:
                session.close()

            return jsonify({
                "status": True,
                "status_code": 200,
                "message": "Fetched all material descriptions",
                "data": material_list
            }), 200

        # ✅ Normalize keys (handle variations)
        normalized_payload = {
            k.lower().replace(" ", "").replace("_", ""): v
            for k, v in payload.items()
        }

        # ✅ Extract material_description
        material_input = None
        for key in normalized_payload.keys():
            if "materialdescription" in key:
                material_input = normalized_payload[key]
                break

        if material_input is None:
            return jsonify({
                "status": False,
                "status_code": 400,
                "message": "Missing 'material_description' field (or set 'fetch_all': true)."
            }), 400

        # ✅ Normalize input (string or list)
        materials = []
        if isinstance(material_input, list):
            materials = [m.strip() for m in material_input if isinstance(m, str) and m.strip()]
        elif isinstance(material_input, str):
            if material_input.startswith("[") and material_input.endswith("]"):
                materials = [m.strip().strip('"').strip("'") for m in material_input.strip("[]").split(",")]
            else:
                materials = [material_input.strip()]
        else:
            return jsonify({
                "status": False,
                "status_code": 400,
                "message": "Invalid format for material_description. Expected string or list."
            }), 400

        if not materials:
            return jsonify({
                "status": False,
                "status_code": 400,
                "message": "No valid material descriptions found"
            }), 400

        # ✅ Query suppliers
        session = next(db_session())
        try:
            query = session.query(SupplierDetails).filter(SupplierDetails.active_flag == True)
            or_conditions = [SupplierDetails.material_description.ilike(f"%{m}%") for m in materials]
            query = query.filter(or_(*or_conditions))
            results = query.all()
        finally:
            session.close()

        if not results:
            return jsonify({
                "status": False,
                "status_code": 404,
                "message": "No matching suppliers found",
                "data": []
            }), 404

        # ✅ Group results by material description
        grouped_data = defaultdict(list)
        for r in results:
            grouped_data[r.material_description].append({
                "supplier": r.supplier,
                "supplier_email": r.supplier_email,
                "notes": r.notes,
                "item_code": r.item_code,
                "id": r.id,
                "last_updated": r.last_updated.strftime("%Y-%m-%d %H:%M:%S"),
            })

        data = [
            {"material_description": material, "suppliers": suppliers}
            for material, suppliers in grouped_data.items()
        ]

        return jsonify({
            "status": True,
            "status_code": 200,
            "message": "Suppliers found",
            "data": data
        }), 200

    except Exception as e:
        print("Error:", e)
        return jsonify({
            "error": str(e),
            "status": False,
            "status_code": 500,
            "message": "Error while searching suppliers"
        }), 500


@suppliers_blueprint.route("/search/part-number", methods=["POST"])
def search_supplier_by_part_number():
    try:
        payload = request.get_json() or {}
        print(f"Incoming payload (part/item search): {payload}")

        # Normalize input keys
        normalized_payload = {
            k.lower().replace(" ", "").replace("_", ""): v
            for k, v in payload.items()
        }

        # Detect item_code or part_number from payload
        search_value = None
        for key in normalized_payload:
            if "partnumber" in key or "itemcode" in key:
                search_value = normalized_payload[key]
                break

        if not search_value:
            return jsonify({
                "status": False,
                "status_code": 400,
                "message": "Missing 'part_number' or 'item_code' field."
            }), 400

        # Ensure string
        if not isinstance(search_value, str):
            return jsonify({
                "status": False,
                "status_code": 400,
                "message": "Invalid format. Expected string."
            }), 400

        search_value = search_value.strip().lower()

        # DB Query: match either part_number OR item_code
        session = next(db_session())
        try:
            results = (
                session.query(SupplierDetails)
                .filter(
                    SupplierDetails.active_flag == True,
                    or_(
                        func.lower(func.cast(SupplierDetails.part_number, String)) == search_value,
                        func.lower(func.cast(SupplierDetails.item_code, String)) == search_value
                    )
                )
                .all()
            )
        finally:
            session.close()

        if not results:
            return jsonify({
                "status": False,
                "status_code": 404,
                "message": "No suppliers found for given part number or item code",
                "data": []
            }), 404

        # Prepare output
        suppliers = []
        for r in results:
            suppliers.append({
                "material_description": r.material_description,
                "supplier": r.supplier,
                "supplier_email": r.supplier_email,
                "item_code": r.item_code,
                "part_number": r.part_number,
                "id": r.id,
            })

        return jsonify({
            "status": True,
            "status_code": 200,
            "message": "Suppliers found",
            "data": suppliers
        }), 200

    except Exception as e:
        print("Error:", e)
        return jsonify({
            "error": str(e),
            "status": False,
            "status_code": 500,
            "message": "Error while searching suppliers"
        }), 500


@suppliers_blueprint.route("/fetch-by-company", methods=["POST"])
def fetch_supplier_by_company():
    """
    Fetch all supplier details based on company name.
    
    Request body:
    {
        "company_name": "Company Name"  (or "supplier": "Company Name")
    }
    
    Response:
    {
        "status": true,
        "message": "Supplier data fetched successfully",
        "data": [
            {
                "id": 1,
                "item_code": "...",
                "material_description": "...",
                "supplier": "Company Name",
                "supplier_email": "...",
                "notes": "...",
                "part_number": "...",
                "active_flag": true,
                "last_updated": "2026-04-28 10:30:00"
            }
        ]
    }
    """
    session = next(db_session())
    try:
        data = request.get_json() or {}
        
        # Extract company_name from various possible field names (accept manufacturer_name too)
        company_name = (
            data.get("company_name") or
            data.get("manufacturer_name") or
            data.get("supplier") or
            data.get("company")
        )

        if not company_name:
            return jsonify({
                "status": False,
                "message": "Missing required parameter: 'company_name', 'manufacturer_name', 'supplier', or 'company'",
                "data": []
            }), 400
        
        # Search for suppliers by company name (supplier field)
        suppliers = session.query(SupplierDetails).filter(
            SupplierDetails.company_name.ilike(f"%{company_name}%")
        ).all()

        if not suppliers:
            return jsonify({
                "status": False,
                "message": f"No suppliers found for company: {company_name}",
                "data": []
            }), 404

        # Return all rows with column names and values
        return jsonify({
            "status": True,
            "message": "Supplier data fetched successfully",
            "data": [
                {
                    "company_name": s.company_name,
                    "company_owner": s.company_owner,
                    "supplier_name": s.supplier_name,
                    "phone_number": s.phone_number,
                    "supplier_email": s.supplier_email,
                    "city": s.city,
                    "country_region": s.country_region,
                    "pincode": s.pincode,
                    "address": s.address
                }
                for s in suppliers
            ]
        }), 200

    except Exception as e:
        print(f"Error fetching suppliers: {str(e)}")
        return jsonify({
            "status": False,
            "error": str(e),
            "message": "Error while fetching supplier details"
        }), 500
    finally:
        session.close()
