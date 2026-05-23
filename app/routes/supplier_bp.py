# from flask import Blueprint, request, jsonify
# from datetime import datetime
# from app.models import SupplierQuotation,SupplierQuotationLineItem, SupplierQuotations
# from app.models import RfqLineItems
# from app.database.DatabaseOperationPostgreSQL import db_session
# from sqlalchemy.exc import SQLAlchemyError
# from sqlalchemy import func, or_
# from logging_config import setup_logging
# import re
# from decimal import Decimal
# from rapidfuzz import fuzz, process

# logger = setup_logging("Supplier_Quotations_Routes", level="DEBUG")


# supplier_bp = Blueprint("supplier_bp", __name__)

# # # ✅ 1️⃣ Add Supplier Quotation
# # @supplier_bp.route("/add", methods=["POST"])
# # def add_supplier_quotation():
# #     try:
# #         data = request.get_json() or {}
# #         print(f"📥 Incoming Payload: {data}")

# #         # ✅ Required fields validation
# #         required_fields = ["rfq_no", "supplier_email", "supplier_name"]
# #         missing = [f for f in required_fields if f not in data or not data[f]]
# #         if missing:
# #             return jsonify({
# #                 "status": False,
# #                 "status_code": 400,
# #                 "message": f"Missing required fields: {', '.join(missing)}"
# #             }), 400

# #         session = next(db_session())
# #         try:
# #             quotation = SupplierQuotations(
# #                 rfq_no=data["rfq_no"],                         # ✅ Correct field
# #                 supplier_email=data["supplier_email"],
# #                 supplier_name=data["supplier_name"],
# #                 quotation_file_path=data.get("quotation_file_path"),
# #                 lead_time_days=data.get("lead_time_days"),
# #                 offered_quantity=data.get("offered_quantity"),
# #                 unit_price=data.get("unit_price"),
# #                 currency=data.get("currency", "INR"),
# #                 status=data.get("status", "Pending"),
# #                 evaluation_reason=data.get("evaluation_reason"),
# #                 notified=data.get("notified", False),
# #                 remarks=data.get("remarks"),
# #                 last_updated=datetime.utcnow(),
# #                 margin=data.get("margin"),
# #                 margin_amount=data.get("margin_amount"),
# #                 total_amount=data.get("total_amount"),
# #                 final_amount=data.get("final_amount")
# #             )
# #             session.add(quotation)
# #             session.commit()
# #         finally:
# #             session.close()

# #         return jsonify({
# #             "status": True,
# #             "status_code": 201,
# #             "message": "Supplier quotation added successfully"
# #         }), 201

# #     except Exception as e:
# #         print("❌ Error in add_supplier_quotation:", e)
# #         return jsonify({
# #             "status": False,
# #             "status_code": 500,
# #             "message": "Error while adding supplier quotation",
# #             "error": str(e)
# #         }), 500

# # @supplier_bp.route("/update", methods=["POST"])
# # def update_supplier_quotation():
# #     session = next(db_session())
# #     try:
# #         data = request.get_json()
# #         rfq_no = data.get("rfq_no")
# #         supplier_email = data.get("supplier_email")
# #         logger.info(f"Update request received for RFQ: {rfq_no}, Supplier: {supplier_email}")

# #         update_fields = [
# #             "quotation_file_path",
# #             "lead_time_days",
# #             "offered_quantity",
# #             "unit_price",
# #             "status",
# #             "margin",
# #             "margin_amount",
# #             "total_amount",   
# #             "final_amount"   
# #         ]

# #         quotations = session.query(SupplierQuotations).filter_by(
# #             rfq_no=rfq_no, supplier_email=supplier_email
# #         ).all()

# #         if not quotations:
# #             logger.warning(f"No quotations found for RFQ {rfq_no}, Supplier {supplier_email}")

# #             return jsonify({"status": False, "message": "No quotations found"}), 404

# #         for q in quotations:
# #             for field in update_fields:
# #                 if field in data:
# #                     value = data[field]
# #                     # sanitize lead_time_days
# #                     if field == "lead_time_days" and isinstance(value, str):
# #                         value = int(''.join(filter(str.isdigit, value)) or 0)
# #                     setattr(q, field, value)
# #                     logger.info(f"Updated {field} to {value} for quotation ID {q.id}")

# #             q.last_updated = datetime.utcnow()

# #         session.commit()

# #         return jsonify({
# #             "status": True,
# #             "status_code": 200,
# #             "message": f"Supplier quotation(s) for RFQ {rfq_no} and {supplier_email} updated successfully."
# #         }), 200

# #     except SQLAlchemyError as db_err:
# #         session.rollback()
# #         print("❌ Database Error:", db_err)
# #         return jsonify({
# #             "status": False,
# #             "status_code": 500,
# #             "message": f"Database error: {str(db_err)}"
# #         }), 500

# #     except Exception as e:
# #         session.rollback()
# #         print("❌ Unexpected Error:", e)
# #         return jsonify({
# #             "status": False,
# #             "status_code": 500,
# #             "message": f"Unexpected error: {str(e)}"
# #         }), 500

# # # ✅ 3️⃣ Get Supplier Quotations by RFQ No
# # @supplier_bp.route("/get/<rfq_no>", methods=["GET"])
# # def get_supplier_quotations(rfq_no):
# #     try:
# #         print(f"🔍 Fetching quotations for RFQ: {rfq_no}")

# #         session = next(db_session())
# #         try:
# #             quotations = session.query(SupplierQuotations).filter_by(rfq_no=rfq_no).all()
# #         finally:
# #             session.close()

# #         if not quotations:
# #             return jsonify({
# #                 "status": False,
# #                 "status_code": 404,
# #                 "message": "No supplier quotations found for this RFQ number",
# #                 "data": []
# #             }), 404

# #         quotation_list = [
# #             {
# #                 "id": q.id,
# #                 "rfq_no": q.rfq_no,                           # ✅ Correct field
# #                 "supplier_email": q.supplier_email,
# #                 "supplier_name": q.supplier_name,
# #                 "quotation_file_path": q.quotation_file_path,
# #                 "lead_time_days": q.lead_time_days,
# #                 "offered_quantity": q.offered_quantity,
# #                 "unit_price": str(q.unit_price) if q.unit_price is not None else None,
# #                 "currency": q.currency,
# #                 "status": q.status,
# #                 "evaluation_reason": q.evaluation_reason,
# #                 "margin_amount": float(q.margin_amount) if q.margin_amount is not None else None,
# #                 "total_amount": float(q.total_amount) if q.total_amount is not None else None,
# #                 "final_amount": float(q.final_amount) if q.final_amount is not None else None,
# #                 "notified": q.notified,
# #                 "remarks": q.remarks,
# #                 "margin": str(q.margin) if q.margin is not None else None,
# #                 "last_updated": q.last_updated.strftime("%Y-%m-%d %H:%M:%S")
# #                     if q.last_updated else None
# #             }
# #             for q in quotations
# #         ]

# #         return jsonify({
# #             "status": True,
# #             "status_code": 200,
# #             "message": "Supplier quotations retrieved successfully",
# #             "data": quotation_list
# #         }), 200

# #     except Exception as e:
# #         print("❌ Error in get_supplier_quotations:", e)
# #         return jsonify({
# #             "status": False,
# #             "status_code": 500,
# #             "message": "Error while fetching supplier quotations",
# #             "error": str(e)
# #         }), 500

# @supplier_bp.route("/add", methods=["POST"])
# def add_supplier_quotation():
#     try:
#         data = request.get_json() or {}
#         print(f"📥 Incoming Payload: {data}")

#         # SAME validation signature
#         required_fields = ["rfq_no", "supplier_email", "supplier_name"]
#         missing = [f for f in required_fields if not data.get(f)]
#         if missing:
#             return jsonify({
#                 "status": False,
#                 "status_code": 400,
#                 "message": f"Missing required fields: {', '.join(missing)}"
#             }), 400

#         session = next(db_session())
#         try:
#             # 🔹 HEADER
#             quotation = SupplierQuotation(
#                 sys_rfq_id=data["rfq_no"],
#                 supplier_name=data["supplier_name"],
#                 supplier_email=data.get("supplier_email"),
#                 supplier_currency=data.get("currency"),
#                 status=data.get("status", "Pending"),
#                 remarks=data.get("remarks"),
#                 quotation_file_path=data.get("quotation_file_path"),
#                 accessible_dangerous_goods=data.get("accessible_dangerous_goods")
#             )
#             session.add(quotation)
#             session.flush()  # 🔑 get supplier_quotation_id

#             # 🔹 LINE ITEM (old header material fields moved here)
#             line_item = SupplierQuotationLineItem(
#                 supplier_quotation_id=quotation.supplier_quotation_id,
#                 material_no=data.get("material_no"),
#                 material_description=data.get("material_description"),
#                 offered_quantity=data.get("offered_quantity"),
#                 price_per_unit=data.get("unit_price"),
#                 lead_time=data.get("lead_time_days")
#             )
#             session.add(line_item)

#             session.commit()
#         finally:
#             session.close()

#         return jsonify({
#             "status": True,
#             "status_code": 201,
#             "message": "Supplier quotation added successfully"
#         }), 201

#     except Exception as e:
#         print("❌ Error in add_supplier_quotation:", e)
#         return jsonify({
#             "status": False,
#             "status_code": 500,
#             "message": "Error while adding supplier quotation",
#             "error": str(e)
#         }), 500



# @supplier_bp.route("/get/<rfq_no>", methods=["GET"])
# def get_supplier_quotations(rfq_no):
#     try:
#         session = next(db_session())

#         quotations = session.query(SupplierQuotation).filter_by(
#             sys_rfq_id=rfq_no
#         ).all()

#         if not quotations:
#             return jsonify({
#                 "status": False,
#                 "status_code": 404,
#                 "message": "No supplier quotations found",
#                 "data": []
#             }), 404

#         result = []

#         for q in quotations:
#             items = session.query(SupplierQuotationLineItem).filter_by(
#                 supplier_quotation_id=q.supplier_quotation_id
#             ).all()

#             for item in items:
#                 result.append({
#                     "id": q.supplier_quotation_id,
#                     "rfq_no": q.sys_rfq_id,
#                     "supplier_email": q.supplier_email,
#                     "supplier_name": q.supplier_name,
#                     "quotation_file_path": q.quotation_file_path,
#                     "offered_quantity": float(item.offered_quantity) if item.offered_quantity else None,
#                     "unit_price": float(item.price_per_unit) if item.price_per_unit else None,
#                     "lead_time_days": item.lead_time,
#                     "currency": q.supplier_currency,
#                     "status": q.status,
#                     "remarks": q.remarks,
#                     "last_updated": q.updated_at.strftime("%Y-%m-%d %H:%M:%S")
#                 })

#         return jsonify({
#             "status": True,
#             "status_code": 200,
#             "message": "Supplier quotations retrieved successfully",
#             "data": result
#         }), 200

#     except Exception as e:
#         return jsonify({
#             "status": False,
#             "status_code": 500,
#             "message": str(e)
#         }), 500
#     finally:
#         session.close()


# @supplier_bp.route("/quotation/create", methods=["POST"])
# def create_supplier_quotation_with_refs():
#     session = next(db_session())
#     try:
#         data = request.get_json() or {}

#         # REQUIRED
#         sys_rfq_id = data.get("sys_rfq_id")
#         supplier_name = data.get("supplier_name")
#         rfq_line_ids = data.get("rfq_line_ids", [])
        
#         existing = session.query(SupplierQuotation).filter_by(
#             sys_rfq_id=sys_rfq_id,
#             supplier_name=supplier_name
#         ).first()

#         if existing:
#             return jsonify({
#                 "status": True,
#                 "message": "Supplier quotation already exists",
#                 "data": {
#                     "supplier_quotation_id": existing.supplier_quotation_id,
#                     "sys_rfq_id": sys_rfq_id,
#                     "linked_line_items": rfq_line_ids
#                 }
#             }), 200


#         if isinstance(rfq_line_ids, str):
#             rfq_line_ids = [rfq_line_ids]

#         if not sys_rfq_id or not supplier_name or not rfq_line_ids:
#             return jsonify({
#                 "status": False,
#                 "message": "sys_rfq_id, supplier_name and rfq_line_ids are required"
#             }), 400

#         # 🔹 Create header
#         quotation = SupplierQuotation(
#             sys_rfq_id=sys_rfq_id,
#             supplier_name=supplier_name,
#             supplier_email=data.get("supplier_email"),
#             supplier_country=data.get("supplier_country"),
#             supplier_currency=data.get("supplier_currency"),
#             exchange_rate=data.get("exchange_rate"),
#             status=data.get("status", "Pending"),
#             remarks=data.get("remarks")
#         )

#         session.add(quotation)
#         session.flush()  # get supplier_quotation_id

#         # 🔹 Create reference-only line items
#         for rfq_line_id in rfq_line_ids:
#             line = SupplierQuotationLineItem(
#                 supplier_quotation_id=quotation.supplier_quotation_id,
#                 rfq_line_id=rfq_line_id
#             )
#             session.add(line)

#         session.commit()

#         return jsonify({
#             "status": True,
#             "message": "Supplier quotation created successfully",
#             "data": {
#                 "supplier_quotation_id": quotation.supplier_quotation_id,
#                 "sys_rfq_id": sys_rfq_id,
#                 "linked_line_items": rfq_line_ids
#             }
#         }), 201

#     except Exception as e:
#         session.rollback()
#         return jsonify({
#             "status": False,
#             "message": str(e)
#         }), 500
#     finally:
#         session.close()

# @supplier_bp.route("/quotation/<supplier_quotation_id>", methods=["GET"])
# def get_supplier_quotation(supplier_quotation_id):
#     session = next(db_session())
#     try:
#         quotation = session.query(SupplierQuotation).get(supplier_quotation_id)
#         if not quotation:
#             return jsonify({"status": False, "message": "Quotation not found"}), 404

#         items = (
#             session.query(SupplierQuotationLineItem, RfqLineItems)
#             .join(RfqLineItems, SupplierQuotationLineItem.rfq_line_id == RfqLineItems.rfq_line_id)
#             .filter(SupplierQuotationLineItem.supplier_quotation_id == supplier_quotation_id)
#             .all()
#         )

#         return jsonify({
#             "status": True,
#             "data": {
#                 "supplier_quotation_id": quotation.supplier_quotation_id,
#                 "sys_rfq_id": quotation.sys_rfq_id,
#                 "supplier_name": quotation.supplier_name,
#                 "supplier_currency": quotation.supplier_currency,
#                 "exchange_rate": quotation.exchange_rate,
#                 "status": quotation.status,
#                 "remarks": quotation.remarks,
#                 "line_items": [
#                     {
#                         "rfq_line_id": rfq.rfq_line_id,
#                         "customer_part_number": rfq.customer_part_number,
#                         "product_description": rfq.product_description,
#                         "quantity": float(rfq.quantity),
#                         "uom": rfq.uom
#                     }
#                     for _, rfq in items
#                 ]
#             }
#         }), 200
#     finally:
#         session.close()

# @supplier_bp.route("/quotation/update-by-rfq", methods=["POST"])
# def update_supplier_quotation_by_rfq():
#     session = next(db_session())
#     try:
#         data = request.get_json() or {}

#         sys_rfq_id = data.get("sys_rfq_id")
#         supplier_name = data.get("supplier_name")

#         if not sys_rfq_id or not supplier_name:
#             return jsonify({
#                 "status": False,
#                 "message": "sys_rfq_id and supplier_name are required"
#             }), 400

#         # 🔹 Find supplier quotation
#         quotation = (
#             session.query(SupplierQuotation)
#             .filter(
#                 SupplierQuotation.sys_rfq_id == sys_rfq_id,
#                 SupplierQuotation.supplier_name == supplier_name
#             )
#             .one_or_none()
#         )

#         if not quotation:
#             return jsonify({
#                 "status": False,
#                 "message": "Supplier quotation not found"
#             }), 404

#         # 🔹 Add header info ONLY if empty
#         header = data.get("header", {})
#         for field in [
#             "supplier_email",
#             "supplier_country",
#             "customer_rfq_number",
#             "quotation_file_path",
#             "local_delivery_partner",
#             "local_delivery_partner_type",
#             "freight_delivery_partner",
#             "freight_delivery_partner_type",
#             "accessible_dangerous_goods"
#         ]:
#             if field in header and getattr(quotation, field) is None:
#                 setattr(quotation, field, header[field])
                
#         processed_rfq_lines = set()

#         # 🔹 Update ONLY specified line items
#         for item in data.get("line_items", []):
#             rfq_line_id = item.get("rfq_line_id")
#             if not rfq_line_id:
#                 continue
            
#             # 🚫 Skip invalid or duplicate RFQ lines
#             if not rfq_line_id or rfq_line_id in processed_rfq_lines:
#                 continue

#             processed_rfq_lines.add(rfq_line_id)

#             line = (
#                 session.query(SupplierQuotationLineItem)
#                 .join(SupplierQuotation)
#                 .filter(
#                     SupplierQuotation.sys_rfq_id == sys_rfq_id,
#                     SupplierQuotation.supplier_name == supplier_name,
#                     SupplierQuotationLineItem.rfq_line_id == rfq_line_id
#                 )
#                 .one_or_none()
#             )

#             if not line:
#                 continue

#             for field in [
#                 "offered_quantity",
#                 "price_per_unit",
#                 "lead_time",
#                 "hsn_code",
#                 "weight_of_package",
#                 "dim_of_package"
#             ]:
#                 if field in item:
#                     setattr(line, field, item[field])

#         # 🔹 Optional status update
#         quotation.status = "Received"

#         session.commit()

#         return jsonify({
#             "status": True,
#             "message": "Supplier quotation updated successfully"
#         }), 200

#     except Exception as e:
#         session.rollback()
#         return jsonify({
#             "status": False,
#             "message": str(e)
#         }), 500
#     finally:
#         session.close()



# @supplier_bp.route("/quotation/fetch-all-by-rfq/<sys_rfq_id>", methods=["GET"])
# def get_supplier_quotations_by_rfq(sys_rfq_id):
#     session = next(db_session())
#     try:
#         quotations = (
#             session.query(SupplierQuotation)
#             .filter(
#                 SupplierQuotation.sys_rfq_id == sys_rfq_id
#             )
#             .ll()
#         )

#         if not quotations:
#             return jsonify({
#                 "status": False,
#                 "message": "No supplier quotations found for this RFQ"
#             }), 404

#         return jsonify({
#             "status": True,
#             "data": [
#                 {
#                     "supplier_quotation_id": q.supplier_quotation_id,
#                     "sys_rfq_id": q.sys_rfq_id,
#                     "supplier_name": q.supplier_name,
#                     "supplier_email": q.supplier_email,
#                     "supplier_country": q.supplier_country,
#                     "customer_rfq_number": q.customer_rfq_number,
#                     "supplier_currency": q.supplier_currency,
#                     "exchange_rate": float(q.exchange_rate) if q.exchange_rate else None,
#                     "local_delivery_partner": q.local_delivery_partner,
#                     "local_delivery_partner_type": q.local_delivery_partner_type,
#                     "freight_delivery_partner": q.freight_delivery_partner,
#                     "freight_delivery_partner_type": q.freight_delivery_partner_type,
#                     "accessible_dangerous_goods": q.accessible_dangerous_goods,
#                     "status": q.status,
#                     "remarks": q.remarks,
#                     "quotation_file_path": q.quotation_file_path,
#                     "created_at": q.created_at,
#                     "updated_at": q.updated_at
#                 }
#                 for q in quotations
#             ]
#         }), 200

#     finally:
#         session.close()


# @supplier_bp.route("/quotation/details-by-rfq/<sys_rfq_id>", methods=["GET"])
# def get_supplier_quotation_details_by_rfq(sys_rfq_id):
#     """
#     Unified RFQ-wise supplier quotation endpoint.
#     Combines new flow (supplier_quotations_new) + legacy flow (supplier_quotations)
#     so frontend can always render Supplier Quotations section.
#     """
#     session = next(db_session())
#     try:
#         rfq_key_norm = (sys_rfq_id or "").strip().lower()

#         # New flow records
#         new_rows = (
#             session.query(SupplierQuotation)
#             .filter(
#                 or_(
#                     func.lower(func.trim(SupplierQuotation.sys_rfq_id)) == rfq_key_norm,
#                     func.lower(func.trim(SupplierQuotation.customer_rfq_number)) == rfq_key_norm,
#                 )
#             )
#             .all()
#         )

#         new_data = [
#             {
#                 "supplier_quotation_id": q.supplier_quotation_id,
#                 "sys_rfq_id": q.sys_rfq_id,
#                 "supplier_name": q.supplier_name,
#                 "supplier_email": q.supplier_email,
#                 "supplier_country": q.supplier_country,
#                 "supplier_currency": q.supplier_currency,
#                 "status": q.status,
#                 "remarks": q.remarks,
#                 "quotation_file_path": q.quotation_file_path,
#                 "created_at": q.created_at,
#                 "updated_at": q.updated_at,
#                 "source_table": "supplier_quotations_new",
#             }
#             for q in new_rows
#         ]

#         # Legacy flow records
#         legacy_rows = (
#             session.query(SupplierQuotations)
#             .filter(func.lower(func.trim(SupplierQuotations.rfq_no)) == rfq_key_norm)
#             .all()
#         )

#         legacy_data = [
#             {
#                 "supplier_quotation_id": str(q.id),
#                 "sys_rfq_id": q.rfq_no,
#                 "supplier_name": q.supplier_name,
#                 "supplier_email": q.supplier_email,
#                 "supplier_country": None,
#                 "supplier_currency": q.currency,
#                 "status": q.status,
#                 "remarks": q.remarks,
#                 "quotation_file_path": q.quotation_file_path,
#                 "created_at": q.last_updated,
#                 "updated_at": q.last_updated,
#                 "source_table": "supplier_quotations",
#             }
#             for q in legacy_rows
#         ]

#         data = new_data if new_data else legacy_data

#         return jsonify({
#             "status": True,
#             "status_code": 200,
#             "message": "Supplier quotation details fetched successfully",
#             "data": data,
#         }), 200
#     except Exception as e:
#         return jsonify({
#             "status": False,
#             "status_code": 500,
#             "message": "Failed to fetch supplier quotation details",
#             "error": str(e),
#         }), 500
#     finally:
#         session.close()


# @supplier_bp.route("/quotation/counts/<sys_rfq_id>", methods=["GET"])
# def get_supplier_quotation_counts(sys_rfq_id):
#     """
#     Returns RFQ-wise quotation progress for RFQ Management page.
#     Example display: 5/10 (received/total)
#     """
#     session = next(db_session())
#     try:
#         rfq_key = (sys_rfq_id or "").strip()
#         rfq_key_norm = rfq_key.lower()

#         # New flow table: supplier_quotations_new
#         new_total_count = (
#             session.query(func.count(SupplierQuotation.supplier_quotation_id))
#             .filter(
#                 or_(
#                     func.lower(func.trim(SupplierQuotation.sys_rfq_id)) == rfq_key_norm,
#                     func.lower(func.trim(SupplierQuotation.customer_rfq_number)) == rfq_key_norm,
#                 )
#             )
#             .scalar()
#         ) or 0

#         new_received_count = (
#             session.query(func.count(SupplierQuotation.supplier_quotation_id))
#             .filter(
#                 or_(
#                     func.lower(func.trim(SupplierQuotation.sys_rfq_id)) == rfq_key_norm,
#                     func.lower(func.trim(SupplierQuotation.customer_rfq_number)) == rfq_key_norm,
#                 ),
#                 or_(
#                     func.lower(func.trim(SupplierQuotation.status)) == "received",
#                     SupplierQuotation.quotation_file_path.isnot(None),
#                 ),
#             )
#             .scalar()
#         ) or 0

#         # If quotation_file_path has empty string values, exclude them from received.
#         if new_received_count:
#             new_received_count = (
#                 session.query(func.count(SupplierQuotation.supplier_quotation_id))
#                 .filter(
#                     or_(
#                         func.lower(func.trim(SupplierQuotation.sys_rfq_id)) == rfq_key_norm,
#                         func.lower(func.trim(SupplierQuotation.customer_rfq_number)) == rfq_key_norm,
#                     ),
#                     or_(
#                         func.lower(func.trim(SupplierQuotation.status)) == "received",
#                         func.length(func.trim(SupplierQuotation.quotation_file_path)) > 0,
#                     ),
#                 )
#                 .scalar()
#             ) or 0

#         # Legacy flow table: supplier_quotations
#         legacy_total_count = (
#             session.query(func.count(SupplierQuotations.id))
#             .filter(func.lower(func.trim(SupplierQuotations.rfq_no)) == rfq_key_norm)
#             .scalar()
#         ) or 0

#         legacy_received_count = (
#             session.query(func.count(SupplierQuotations.id))
#             .filter(
#                 func.lower(func.trim(SupplierQuotations.rfq_no)) == rfq_key_norm,
#                 or_(
#                     func.lower(func.trim(SupplierQuotations.status)) == "received",
#                     func.length(func.trim(SupplierQuotations.quotation_file_path)) > 0,
#                 ),
#             )
#             .scalar()
#         ) or 0

#         # Use whichever flow has data for this RFQ.
#         if new_total_count > 0:
#             total_count = new_total_count
#             received_count = new_received_count
#             source_table = "supplier_quotations_new"
#         elif legacy_total_count > 0:
#             total_count = legacy_total_count
#             received_count = legacy_received_count
#             source_table = "supplier_quotations"
#         else:
#             total_count = 0
#             received_count = 0
#             source_table = "none"

#         return jsonify({
#             "status": True,
#             "status_code": 200,
#             "message": "Supplier quotation counts fetched successfully",
#             "data": {
#                 "sys_rfq_id": sys_rfq_id,
#                 "received_count": int(received_count),
#                 "total_count": int(total_count),
#                 "display_count": f"{int(received_count)}/{int(total_count)}",
#                 "source_table": source_table
#             }
#         }), 200
#     except Exception as e:
#         return jsonify({
#             "status": False,
#             "status_code": 500,
#             "message": "Failed to fetch supplier quotation counts",
#             "error": str(e)
#         }), 500
#     finally:
#         session.close()






# # utils_normalization.p
# def parse_decimal(value):
#     """
#     Converts:
#     'INR 1,200.50', '1,200.50', '1200.50', 1200, 1200.5 → Decimal
#     """
#     if value is None:
#         return None

#     if isinstance(value, Decimal):
#         return value

#     if isinstance(value, (int, float)):
#         return Decimal(str(value))

#     s = str(value)

#     # 🔥 KEY FIX: remove commas BEFORE parsing
#     s = s.replace(",", "")

#     match = re.search(r"\d+(\.\d+)?", s)
#     if not match:
#         return None

#     try:
#         return Decimal(match.group())
#     except Exception:
#         return None

# def parse_quantity(value):
#     """
#     Converts:
#     '16 Nos', '16', 16 → Decimal
#     """
#     return parse_decimal(value)


# def normalize_string(s):
#     """Normalize string for comparison: uppercase, no spaces, no hyphens"""
#     if not s:
#         return ""
#     return str(s).strip().upper().replace(" ", "").replace("-", "")


# def normalize_boolean(value):
#     """Convert string boolean to actual boolean"""
#     if isinstance(value, bool):
#         return value
#     if isinstance(value, str):
#         return value.lower() in ["true", "1", "yes", "y"]
#     return False


# def get_first_present(d: dict, *keys):
#     """
#     Returns the first non-null value from a dict for given keys.
#     Supports LLM aliases safely.
#     """
#     for k in keys:
#         if k in d and d[k] is not None:
#             return d[k]
#     return None



# # def normalize_string(s):
# #     """Normalize string for comparison: uppercase, no spaces"""
# #     if not s:
# #         return ""
# #     return str(s).strip().upper().replace(" ", "").replace("-", "")


# # def normalize_boolean(value):
# #     """Convert string boolean to actual boolean"""
# #     if isinstance(value, bool):
# #         return value
# #     if isinstance(value, str):
# #         return value.lower() in ['true', '1', 'yes', 'y']
# #     return False

# def find_supplier_quotation(session, rfq_id, supplier_name, supplier_email=None):
#     all_quotations = (
#         session.query(SupplierQuotation)
#         .filter(SupplierQuotation.sys_rfq_id == rfq_id)
#         .all()
#     )

#     if not all_quotations:
#         return None, {"error": "No quotations found for this RFQ"}

#     # 1. Exact email match
#     if supplier_email:
#         for quotation in all_quotations:
#             if quotation.supplier_email and quotation.supplier_email.lower().strip() == supplier_email.lower().strip():
#                 return quotation, {
#                     "method": "exact_email",
#                     "confidence": 100,
#                     "matched_name": quotation.supplier_name
#                 }

#     # 2. Exact name match
#     for quotation in all_quotations:
#         if quotation.supplier_name.lower().strip() == supplier_name.lower().strip():
#             return quotation, {
#                 "method": "exact_name",
#                 "confidence": 100,
#                 "matched_name": quotation.supplier_name
#             }

#     # 3. Fuzzy match
#     supplier_names = [q.supplier_name for q in all_quotations]
#     best_match = process.extractOne(supplier_name, supplier_names, scorer=fuzz.token_sort_ratio)

#     if best_match:
#         name, score, index = best_match
#         if score >= 85:
#             return all_quotations[index], {
#                 "method": "fuzzy_name",
#                 "confidence": score,
#                 "matched_name": name
#             }

#     return None, {"error": "No matching supplier found"}

# # def build_material_mapping(session, rfq_id):
# #     """
# #     Build mapping from RFQ line items to enable material matching.
    
# #     Returns:
# #         dict with:
# #         - manufacturer_part_map: normalized manufacturer part -> rfq_line_id
# #         - customer_part_map: normalized customer part -> rfq_line_id
# #         - description_map: product description -> rfq_line_id
# #         - duplicate_parts: dict of duplicate manufacturer parts (for warnings)
# #     """
# #     rfq_lines = (
# #         session.query(RfqLineItems)
# #         .filter(
# #             RfqLineItems.sys_rfq_id == rfq_id,
# #             RfqLineItems.deleted_flag == False
# #         )
# #         .all()
# #     )

# #     if not rfq_lines:
# #         logger.warning(f"No RFQ line items found for {rfq_id}")
# #         return {
# #             "manufacturer_part_map": {},
# #             "customer_part_map": {},
# #             "description_map": {},
# #             "duplicate_parts": {}
# #         }

# #     manufacturer_part_map = {}
# #     customer_part_map = {}
# #     description_map = {}
# #     duplicate_parts = {}  # Track duplicate manufacturer parts

# #     for line in rfq_lines:
# #         # Customer part number mapping
# #         if line.customer_part_number:
# #             normalized_customer = normalize_string(line.customer_part_number)
# #             if normalized_customer:
# #                 customer_part_map[normalized_customer] = line.rfq_line_id

# #         # Manufacturer part number mapping (from mapping_json)
# #         if line.mapping_json:
# #             if isinstance(line.mapping_json, list):
# #                 for mapping in line.mapping_json:
# #                     part = mapping.get("manufacturer_product_name")
# #                     if part:
# #                         normalized = normalize_string(part)
# #                         if normalized:
# #                             # Check for duplicates
# #                             if normalized in manufacturer_part_map:
# #                                 if normalized not in duplicate_parts:
# #                                     duplicate_parts[normalized] = [manufacturer_part_map[normalized]]
# #                                 duplicate_parts[normalized].append(line.rfq_line_id)
# #                                 logger.warning(
# #                                     f"Duplicate manufacturer part '{part}' found in RFQ {rfq_id}. "
# #                                     f"Lines: {duplicate_parts[normalized]}"
# #                                 )
# #                             else:
# #                                 manufacturer_part_map[normalized] = line.rfq_line_id
# #             elif isinstance(line.mapping_json, dict):
# #                 # Handle case where mapping_json is a single dict
# #                 part = line.mapping_json.get("manufacturer_product_name")
# #                 if part:
# #                     normalized = normalize_string(part)
# #                     if normalized:
# #                         if normalized in manufacturer_part_map:
# #                             if normalized not in duplicate_parts:
# #                                 duplicate_parts[normalized] = [manufacturer_part_map[normalized]]
# #                             duplicate_parts[normalized].append(line.rfq_line_id)
# #                         else:
# #                             manufacturer_part_map[normalized] = line.rfq_line_id

# #         # Description mapping
# #         if line.product_description:
# #             description_map[line.product_description] = line.rfq_line_id

# #     return {
# #         "manufacturer_part_map": manufacturer_part_map,
# #         "customer_part_map": customer_part_map,
# #         "description_map": description_map,
# #         "duplicate_parts": duplicate_parts
# #     }


# import json

# def build_material_mapping(session, rfq_id):
#     """
#     Build mapping from RFQ line items to enable material matching.
    
#     Returns:
#         dict with:
#         - manufacturer_part_map: normalized manufacturer part -> rfq_line_id
#         - customer_part_map: normalized customer part -> rfq_line_id
#         - description_map: product description -> rfq_line_id
#         - duplicate_parts: dict of duplicate manufacturer parts (for warnings)
#     """
#     rfq_lines = (
#         session.query(RfqLineItems)
#         .filter(
#             RfqLineItems.sys_rfq_id == rfq_id,
#             RfqLineItems.deleted_flag == False
#         )
#         .all()
#     )

#     if not rfq_lines:
#         logger.warning(f"No RFQ line items found for {rfq_id}")
#         return {
#             "manufacturer_part_map": {},
#             "customer_part_map": {},
#             "description_map": {},
#             "duplicate_parts": {}
#         }

#     manufacturer_part_map = {}
#     customer_part_map = {}
#     description_map = {}
#     duplicate_parts = {}  # Track duplicate manufacturer parts

#     for line in rfq_lines:
#         # ------------------------------------------------------------
#         # Customer part number mapping (UNCHANGED)
#         # ------------------------------------------------------------
#         if line.customer_part_number:
#             normalized_customer = normalize_string(line.customer_part_number)
#             if normalized_customer:
#                 customer_part_map[normalized_customer] = line.rfq_line_id

#         # ------------------------------------------------------------
#         # ADDITIVE NORMALIZATION ONLY (NO LOGIC CHANGE)
#         # Handle mapping_json stored as STRING
#         # ------------------------------------------------------------
#         mapping_json = line.mapping_json
#         if isinstance(mapping_json, str):
#             try:
#                 mapping_json = json.loads(mapping_json)
#             except Exception as e:
#                 logger.error(
#                     f"Invalid mapping_json for RFQ line {line.rfq_line_id}: {e}"
#                 )
#                 mapping_json = None

#         # ------------------------------------------------------------
#         # Manufacturer part number mapping (CORE LOGIC UNCHANGED)
#         # ------------------------------------------------------------
#         if mapping_json:
#             if isinstance(mapping_json, list):
#                 for mapping in mapping_json:
#                     part = mapping.get("manufacturer_product_name")
#                     if part:
#                         normalized = normalize_string(part)
#                         if normalized:
#                             # Check for duplicates
#                             if normalized in manufacturer_part_map:
#                                 if normalized not in duplicate_parts:
#                                     duplicate_parts[normalized] = [
#                                         manufacturer_part_map[normalized]
#                                     ]
#                                 duplicate_parts[normalized].append(line.rfq_line_id)
#                                 logger.warning(
#                                     f"Duplicate manufacturer part '{part}' found in RFQ {rfq_id}. "
#                                     f"Lines: {duplicate_parts[normalized]}"
#                                 )
#                             else:
#                                 manufacturer_part_map[normalized] = line.rfq_line_id

#             elif isinstance(mapping_json, dict):
#                 # Handle case where mapping_json is a single dict
#                 part = mapping_json.get("manufacturer_product_name")
#                 if part:
#                     normalized = normalize_string(part)
#                     if normalized:
#                         if normalized in manufacturer_part_map:
#                             if normalized not in duplicate_parts:
#                                 duplicate_parts[normalized] = [
#                                     manufacturer_part_map[normalized]
#                                 ]
#                             duplicate_parts[normalized].append(line.rfq_line_id)
#                         else:
#                             manufacturer_part_map[normalized] = line.rfq_line_id

#         # ------------------------------------------------------------
#         # Description mapping (UNCHANGED)
#         # ------------------------------------------------------------
#         if line.product_description:
#             description_map[line.product_description] = line.rfq_line_id

#     return {
#         "manufacturer_part_map": manufacturer_part_map,
#         "customer_part_map": customer_part_map,
#         "description_map": description_map,
#         "duplicate_parts": duplicate_parts
#     }


# def match_material_to_rfq_line(material, mapping_data):
#     """
#     Match a single supplier material to an RFQ line item
    
#     Args:
#         material: dict with supplier's material data
#         mapping_data: dict from build_material_mapping()
    
#     Returns:
#         tuple: (rfq_line_id or None, match_info dict)
#     """
#     material_no = material.get('material_no', '')
#     material_desc = material.get('material_description', '')
    
#     normalized_material_no = normalize_string(material_no)
    
#     match_info = {
#         'material_no': material_no,
#         'method': None,
#         'confidence': 0,
#         'rfq_line_id': None
#     }
    
#     # Strategy 1: Manufacturer part number (HIGHEST PRIORITY)
#     if normalized_material_no in mapping_data['manufacturer_part_map']:
#         match_info['rfq_line_id'] = mapping_data['manufacturer_part_map'][normalized_material_no]
#         match_info['method'] = 'manufacturer_part_exact'
#         match_info['confidence'] = 100
#         return match_info['rfq_line_id'], match_info
    
#     # Strategy 2: Customer part number
#     if normalized_material_no in mapping_data['customer_part_map']:
#         match_info['rfq_line_id'] = mapping_data['customer_part_map'][normalized_material_no]
#         match_info['method'] = 'customer_part_exact'
#         match_info['confidence'] = 95
#         return match_info['rfq_line_id'], match_info
    
#     # Strategy 3: Fuzzy match on description (LOWEST PRIORITY)
#     if material_desc and mapping_data['description_map']:
#         best_match = process.extractOne(
#             material_desc,
#             list(mapping_data['description_map'].keys()),
#             scorer=fuzz.token_sort_ratio
#         )
        
#         if best_match and best_match[1] >= 80:  # 80% threshold for descriptions
#             matched_desc = best_match[0]
#             match_info['rfq_line_id'] = mapping_data['description_map'][matched_desc]
#             match_info['method'] = 'description_fuzzy'
#             match_info['confidence'] = best_match[1]
#             match_info['matched_description'] = matched_desc
#             return match_info['rfq_line_id'], match_info
    
#     # No match found
#     match_info['method'] = 'no_match'
#     match_info['reason'] = 'Material not found in RFQ line items'
#     return None, match_info




# @supplier_bp.route("/supplier-quotation/update", methods=["POST"])
# def update_supplier_quotation():
#     session = next(db_session())

#     try:
#         data = request.get_json()
#         if not data:
#             return jsonify({"success": False, "error": "No JSON data provided"}), 400

#         # ------------------------------------------------------------------
#         # ADDITIVE FIX #1: ROOT-LEVEL PAYLOAD SUPPORT (NO LOGIC CHANGE)
#         # ------------------------------------------------------------------
#         sys_rfq_id = data.get("sys_rfq_id") or data.get("rfq_no")
#         if not sys_rfq_id:
#             return jsonify({"success": False, "error": "sys_rfq_id or rfq_no is required"}), 400

#         supplier_name = data.get("supplier_name")
#         supplier_email = data.get("supplier_email")

#         if not supplier_name:
#             return jsonify({"success": False, "error": "supplier_name is required"}), 400

#         # ------------------------------------------------------------------
#         # EXISTING CORE LOGIC (UNCHANGED)
#         # ------------------------------------------------------------------
#         quotation, supplier_match_info = find_supplier_quotation(
#             session,
#             sys_rfq_id,
#             supplier_name,
#             supplier_email
#         )

#         if not quotation:
#             return jsonify({
#                 "success": False,
#                 "error": "Supplier quotation not found",
#                 "match_info": supplier_match_info
#             }), 404

#         mapping_data = build_material_mapping(session, sys_rfq_id)

#         # ------------------------------------------------------------------
#         # HEADER UPDATE (UNCHANGED LOGIC)
#         # ------------------------------------------------------------------
#         quotation.supplier_currency = data.get("currency")
#         quotation.exchange_rate = data.get("exchange_rate")
#         quotation.supplier_country = data.get("supplier_country")
#         quotation.accessible_dangerous_goods = normalize_boolean(
#             data.get("accessible_dangerous_goods")
#         )
#         quotation.status = "Received"
#         quotation.remarks = data.get("remarks", "Updated from email")
#         quotation.local_delivery_partner = data.get("local_delivery_partner") or None
#         quotation.local_delivery_partner_type = data.get("local_delivery_partner_type") or None
#         quotation.freight_delivery_partner = data.get("freight_delivery_partner") or None
#         quotation.freight_delivery_partner_type = data.get("freight_delivery_partner_type") or None
#         quotation.updated_at = datetime.utcnow()

#         if supplier_email and not quotation.supplier_email:
#             quotation.supplier_email = supplier_email

#         # ------------------------------------------------------------------
#         # MATERIALS (CORE FLOW UNCHANGED)
#         # ------------------------------------------------------------------
#         materials = data.get("materials", [])
#         if not materials:
#             return jsonify({"success": False, "error": "materials are required"}), 400

#         updated_lines = []
#         created_lines = []
#         unmatched_materials = []
#         failed_materials = []
#         match_details = []

#         for material in materials:
#             # ✅ ADDITIVE: isolate each material
#             with session.begin_nested():

#                 material_no = material.get("material_no")
#                 if not material_no:
#                     continue

#                 rfq_line_id = None
#                 match_info = None

#                 try:
#                     # ----------------------------------------------------------
#                     # EXISTING MATCHING LOGIC (UNCHANGED)
#                     # ----------------------------------------------------------
#                     rfq_line_id, match_info = match_material_to_rfq_line(
#                         material, mapping_data
#                     )
#                     match_details.append(match_info)

#                     if not rfq_line_id:
#                         unmatched_materials.append({
#                             "material_no": material_no,
#                             "material_description": material.get("material_description"),
#                             "match_info": match_info
#                         })
#                         continue

#                     supplier_line = (
#                         session.query(SupplierQuotationLineItem)
#                         .filter_by(
#                             supplier_quotation_id=quotation.supplier_quotation_id,
#                             rfq_line_id=rfq_line_id
#                         )
#                         .first()
#                     )

#                     # ----------------------------------------------------------
#                     # ADDITIVE FIX #2: LLM FIELD ALIASES + NORMALIZATION
#                     # ----------------------------------------------------------
#                     offered_qty = parse_quantity(
#                         get_first_present(material, "offered_quantity","required_quantity")
#                     )

#                     price_per_unit = parse_decimal(
#                         get_first_present(material, "price_per_unit", "unit_price")
#                     )

#                     lead_time = get_first_present(
#                         material, "lead_time", "lead_time_days"
#                     )

#                     logger.info(
#                         "Processing material | material_no=%s | rfq_line_id=%s | offered_qty=%s",
#                         material_no,
#                         rfq_line_id,
#                         offered_qty
#                     )

#                     if supplier_line:
#                         supplier_line.rfq_line_id = rfq_line_id
#                         supplier_line.material_no = material_no
#                         supplier_line.material_description = material.get("material_description")
#                         supplier_line.offered_quantity = offered_qty
#                         supplier_line.price_per_unit = price_per_unit
#                         supplier_line.lead_time = lead_time
#                         supplier_line.hsn_code = material.get("hsn_code")
#                         supplier_line.weight_of_package = material.get("weight_of_package")
#                         supplier_line.dim_of_package = material.get("dim_of_package")
#                         supplier_line.updated_at = datetime.utcnow()

#                         logger.info(
#                             "Updated supplier line | rfq_line_id=%s | offered_qty=%s",
#                             rfq_line_id,
#                             supplier_line.offered_quantity
#                         )

#                         updated_lines.append({
#                             "material_no": material_no,
#                             "rfq_line_id": rfq_line_id,
#                             "match_method": match_info.get("method"),
#                             "confidence": match_info.get("confidence")
#                         })

#                     else:
#                         new_line = SupplierQuotationLineItem(
#                             supplier_quotation_id=quotation.supplier_quotation_id,
#                             rfq_line_id=rfq_line_id,
#                             material_no=material_no,
#                             material_description=material.get("material_description"),
#                             offered_quantity=offered_qty,
#                             price_per_unit=price_per_unit,
#                             lead_time=lead_time,
#                             hsn_code=material.get("hsn_code"),
#                             weight_of_package=material.get("weight_of_package"),
#                             dim_of_package=material.get("dim_of_package")
#                         )
#                         session.add(new_line)
#                         session.flush()

#                         logger.info(
#                             "Created supplier line | rfq_line_id=%s | offered_qty=%s",
#                             rfq_line_id,
#                             offered_qty
#                         )

#                         created_lines.append({
#                             "material_no": material_no,
#                             "rfq_line_id": rfq_line_id,
#                             "match_method": match_info.get("method"),
#                             "confidence": match_info.get("confidence")
#                         })

#                 except Exception as material_error:
#                     # ❌ NO GLOBAL ROLLBACK HERE (CRITICAL FIX)
#                     logger.exception(
#                         "Material processing failed | material_no=%s | rfq_line_id=%s",
#                         material_no,
#                         rfq_line_id
#                     )
#                     failed_materials.append({
#                         "material_no": material_no,
#                         "error": str(material_error),
#                         "rfq_line_id": rfq_line_id
#                     })
#                     continue

#         # ------------------------------------------------------------------
#         # COMMIT (UNCHANGED)
#         # ------------------------------------------------------------------
#         logger.info(
#             "Final commit | quotation_id=%s | updated=%d | created=%d | failed=%d",
#             quotation.supplier_quotation_id,
#             len(updated_lines),
#             len(created_lines),
#             len(failed_materials)
#         )

#         session.commit()

#         return jsonify({
#             "success": True,
#             "supplier_matching": supplier_match_info,
#             "updated_lines": updated_lines,
#             "created_lines": created_lines,
#             "unmatched_materials": unmatched_materials,
#             "failed_materials": failed_materials,
#             "match_details": match_details
#         }), 200

#     except Exception as e:
#         session.rollback()
#         logger.exception("Fatal supplier quotation update error")
#         return jsonify({"success": False, "error": str(e)}), 500

#     finally:
#         session.close()
from flask import Blueprint, request, jsonify
from datetime import datetime
from app.models import SupplierQuotation,SupplierQuotationLineItem, SupplierQuotations
from app.models import RfqLineItems, RfqHeader
from app.database.DatabaseOperationPostgreSQL import db_session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import func, or_
from logging_config import setup_logging
import re
from decimal import Decimal
from rapidfuzz import fuzz, process
from app.models.supplier_charges_calculation import SupplierChargesCalculation
logger = setup_logging("Supplier_Quotations_Routes", level="DEBUG")


supplier_bp = Blueprint("supplier_bp", __name__)

# # ✅ 1️⃣ Add Supplier Quotation
# @supplier_bp.route("/add", methods=["POST"])
# def add_supplier_quotation():
#     try:
#         data = request.get_json() or {}
#         print(f"📥 Incoming Payload: {data}")

#         # ✅ Required fields validation
#         required_fields = ["rfq_no", "supplier_email", "supplier_name"]
#         missing = [f for f in required_fields if f not in data or not data[f]]
#         if missing:
#             return jsonify({
#                 "status": False,
#                 "status_code": 400,
#                 "message": f"Missing required fields: {', '.join(missing)}"
#             }), 400

#         session = next(db_session())
#         try:
#             quotation = SupplierQuotations(
#                 rfq_no=data["rfq_no"],                         # ✅ Correct field
#                 supplier_email=data["supplier_email"],
#                 supplier_name=data["supplier_name"],
#                 quotation_file_path=data.get("quotation_file_path"),
#                 lead_time_days=data.get("lead_time_days"),
#                 offered_quantity=data.get("offered_quantity"),
#                 unit_price=data.get("unit_price"),
#                 currency=data.get("currency", "INR"),
#                 status=data.get("status", "Pending"),
#                 evaluation_reason=data.get("evaluation_reason"),
#                 notified=data.get("notified", False),
#                 remarks=data.get("remarks"),
#                 last_updated=datetime.utcnow(),
#                 margin=data.get("margin"),
#                 margin_amount=data.get("margin_amount"),
#                 total_amount=data.get("total_amount"),
#                 final_amount=data.get("final_amount")
#             )
#             session.add(quotation)
#             session.commit()
#         finally:
#             session.close()

#         return jsonify({
#             "status": True,
#             "status_code": 201,
#             "message": "Supplier quotation added successfully"
#         }), 201

#     except Exception as e:
#         print("❌ Error in add_supplier_quotation:", e)
#         return jsonify({
#             "status": False,
#             "status_code": 500,
#             "message": "Error while adding supplier quotation",
#             "error": str(e)
#         }), 500

# @supplier_bp.route("/update", methods=["POST"])
# def update_supplier_quotation():
#     session = next(db_session())
#     try:
#         data = request.get_json()
#         rfq_no = data.get("rfq_no")
#         supplier_email = data.get("supplier_email")
#         logger.info(f"Update request received for RFQ: {rfq_no}, Supplier: {supplier_email}")

#         update_fields = [
#             "quotation_file_path",
#             "lead_time_days",
#             "offered_quantity",
#             "unit_price",
#             "status",
#             "margin",
#             "margin_amount",
#             "total_amount",   
#             "final_amount"   
#         ]

#         quotations = session.query(SupplierQuotations).filter_by(
#             rfq_no=rfq_no, supplier_email=supplier_email
#         ).all()

#         if not quotations:
#             logger.warning(f"No quotations found for RFQ {rfq_no}, Supplier {supplier_email}")

#             return jsonify({"status": False, "message": "No quotations found"}), 404

#         for q in quotations:
#             for field in update_fields:
#                 if field in data:
#                     value = data[field]
#                     # sanitize lead_time_days
#                     if field == "lead_time_days" and isinstance(value, str):
#                         value = int(''.join(filter(str.isdigit, value)) or 0)
#                     setattr(q, field, value)
#                     logger.info(f"Updated {field} to {value} for quotation ID {q.id}")

#             q.last_updated = datetime.utcnow()

#         session.commit()

#         return jsonify({
#             "status": True,
#             "status_code": 200,
#             "message": f"Supplier quotation(s) for RFQ {rfq_no} and {supplier_email} updated successfully."
#         }), 200

#     except SQLAlchemyError as db_err:
#         session.rollback()
#         print("❌ Database Error:", db_err)
#         return jsonify({
#             "status": False,
#             "status_code": 500,
#             "message": f"Database error: {str(db_err)}"
#         }), 500

#     except Exception as e:
#         session.rollback()
#         print("❌ Unexpected Error:", e)
#         return jsonify({
#             "status": False,
#             "status_code": 500,
#             "message": f"Unexpected error: {str(e)}"
#         }), 500

# # ✅ 3️⃣ Get Supplier Quotations by RFQ No
# @supplier_bp.route("/get/<rfq_no>", methods=["GET"])
# def get_supplier_quotations(rfq_no):
#     try:
#         print(f"🔍 Fetching quotations for RFQ: {rfq_no}")

#         session = next(db_session())
#         try:
#             quotations = session.query(SupplierQuotations).filter_by(rfq_no=rfq_no).all()
#         finally:
#             session.close()

#         if not quotations:
#             return jsonify({
#                 "status": False,
#                 "status_code": 404,
#                 "message": "No supplier quotations found for this RFQ number",
#                 "data": []
#             }), 404

#         quotation_list = [
#             {
#                 "id": q.id,
#                 "rfq_no": q.rfq_no,                           # ✅ Correct field
#                 "supplier_email": q.supplier_email,
#                 "supplier_name": q.supplier_name,
#                 "quotation_file_path": q.quotation_file_path,
#                 "lead_time_days": q.lead_time_days,
#                 "offered_quantity": q.offered_quantity,
#                 "unit_price": str(q.unit_price) if q.unit_price is not None else None,
#                 "currency": q.currency,
#                 "status": q.status,
#                 "evaluation_reason": q.evaluation_reason,
#                 "margin_amount": float(q.margin_amount) if q.margin_amount is not None else None,
#                 "total_amount": float(q.total_amount) if q.total_amount is not None else None,
#                 "final_amount": float(q.final_amount) if q.final_amount is not None else None,
#                 "notified": q.notified,
#                 "remarks": q.remarks,
#                 "margin": str(q.margin) if q.margin is not None else None,
#                 "last_updated": q.last_updated.strftime("%Y-%m-%d %H:%M:%S")
#                     if q.last_updated else None
#             }
#             for q in quotations
#         ]

#         return jsonify({
#             "status": True,
#             "status_code": 200,
#             "message": "Supplier quotations retrieved successfully",
#             "data": quotation_list
#         }), 200

#     except Exception as e:
#         print("❌ Error in get_supplier_quotations:", e)
#         return jsonify({
#             "status": False,
#             "status_code": 500,
#             "message": "Error while fetching supplier quotations",
#             "error": str(e)
#         }), 500

@supplier_bp.route("/add", methods=["POST"])
def add_supplier_quotation():
    try:
        data = request.get_json() or {}
        print(f"📥 Incoming Payload: {data}")

        # SAME validation signature
        required_fields = ["rfq_no", "supplier_email", "supplier_name"]
        missing = [f for f in required_fields if not data.get(f)]
        if missing:
            return jsonify({
                "status": False,
                "status_code": 400,
                "message": f"Missing required fields: {', '.join(missing)}"
            }), 400

        session = next(db_session())
        try:
            # 🔹 HEADER
            quotation = SupplierQuotation(
                sys_rfq_id=data["rfq_no"],
                supplier_name=data["supplier_name"],
                supplier_email=data.get("supplier_email"),
                supplier_currency=data.get("currency"),
                status=data.get("status", "Pending"),
                remarks=data.get("remarks"),
                quotation_file_path=data.get("quotation_file_path"),
                accessible_dangerous_goods=data.get("accessible_dangerous_goods")
            )
            session.add(quotation)
            session.flush()  # 🔑 get supplier_quotation_id

            # 🔹 LINE ITEM (old header material fields moved here)
            line_item = SupplierQuotationLineItem(
                supplier_quotation_id=quotation.supplier_quotation_id,
                material_no=data.get("material_no"),
                material_description=data.get("material_description"),
                offered_quantity=data.get("offered_quantity"),
                price_per_unit=data.get("unit_price"),
                lead_time=data.get("lead_time_days")
            )
            session.add(line_item)

            session.commit()
        finally:
            session.close()

        return jsonify({
            "status": True,
            "status_code": 201,
            "message": "Supplier quotation added successfully"
        }), 201

    except Exception as e:
        print("❌ Error in add_supplier_quotation:", e)
        return jsonify({
            "status": False,
            "status_code": 500,
            "message": "Error while adding supplier quotation",
            "error": str(e)
        }), 500


# @supplier_bp.route("/update", methods=["POST"])
# def update_supplier_quotation():
#     session = next(db_session())
#     try:
#         data = request.get_json()
#         rfq_no = data.get("rfq_no")
#         supplier_email = data.get("supplier_email")

#         quotation = session.query(SupplierQuotation).filter_by(
#             sys_rfq_id=rfq_no,
#             supplier_email=supplier_email
#         ).first()

#         if not quotation:
#             return jsonify({"status": False, "message": "No quotation found"}), 404

#         # 🔹 HEADER updates
#         header_fields = [
#             "quotation_file_path",
#             "status",
#             "remarks"
#         ]

#         for field in header_fields:
#             if field in data:
#                 setattr(quotation, field, data[field])

#         quotation.updated_at = datetime.utcnow()

#         # 🔹 LINE ITEM updates
#         line_items = session.query(SupplierQuotationLineItem).filter_by(
#             supplier_quotation_id=quotation.supplier_quotation_id
#         ).all()

#         for item in line_items:
#             if "offered_quantity" in data:
#                 item.offered_quantity = data["offered_quantity"]
#             if "unit_price" in data:
#                 item.price_per_unit = data["unit_price"]
#             if "lead_time_days" in data:
#                 item.lead_time = data["lead_time_days"]

#             item.updated_at = datetime.utcnow()

#         session.commit()

#         return jsonify({
#             "status": True,
#             "status_code": 200,
#             "message": "Supplier quotation updated successfully"
#         }), 200

#     except Exception as e:
#         session.rollback()
#         return jsonify({
#             "status": False,
#             "status_code": 500,
#             "message": str(e)
#         }), 500
#     finally:
#         session.close()


@supplier_bp.route("/get/<rfq_no>", methods=["GET"])
def get_supplier_quotations(rfq_no):
    try:
        session = next(db_session())

        quotations = session.query(SupplierQuotation).filter_by(
            sys_rfq_id=rfq_no
        ).all()

        if not quotations:
            return jsonify({
                "status": False,
                "status_code": 404,
                "message": "No supplier quotations found",
                "data": []
            }), 404

        result = []

        for q in quotations:
            items = session.query(SupplierQuotationLineItem).filter_by(
                supplier_quotation_id=q.supplier_quotation_id
            ).all()

            for item in items:
                result.append({
                    "id": q.supplier_quotation_id,
                    "rfq_no": q.sys_rfq_id,
                    "supplier_email": q.supplier_email,
                    "supplier_name": q.supplier_name,
                    "quotation_file_path": q.quotation_file_path,
                    "offered_quantity": float(item.offered_quantity) if item.offered_quantity else None,
                    "unit_price": float(item.price_per_unit) if item.price_per_unit else None,
                    "lead_time_days": item.lead_time,
                    "currency": q.supplier_currency,
                    "status": q.status,
                    "remarks": q.remarks,
                    "last_updated": q.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                })

        return jsonify({
            "status": True,
            "status_code": 200,
            "message": "Supplier quotations retrieved successfully",
            "data": result
        }), 200

    except Exception as e:
        return jsonify({
            "status": False,
            "status_code": 500,
            "message": str(e)
        }), 500
    finally:
        session.close()


@supplier_bp.route("/quotation/create", methods=["POST"])
def create_supplier_quotation_with_refs():
    session = next(db_session())
    try:
        data = request.get_json() or {}

        # REQUIRED
        sys_rfq_id = data.get("sys_rfq_id")
        supplier_name = data.get("supplier_name")
        rfq_line_ids = data.get("rfq_line_ids", [])

        if isinstance(rfq_line_ids, str):
            rfq_line_ids = [rfq_line_ids]
        rfq_line_ids = [str(x).strip() for x in rfq_line_ids if str(x).strip()]

        if not sys_rfq_id or not supplier_name or not rfq_line_ids:
            return jsonify({
                "status": False,
                "message": "sys_rfq_id, supplier_name and rfq_line_ids are required"
            }), 400

        # Validate RFQ header early to avoid FK 500s
        rfq_exists = session.query(RfqHeader.sys_rfq_id).filter(
            RfqHeader.sys_rfq_id == sys_rfq_id
        ).first()
        if not rfq_exists:
            return jsonify({
                "status": False,
                "message": f"Invalid sys_rfq_id: {sys_rfq_id}"
            }), 400

        # Validate line ids belong to the same RFQ
        valid_line_rows = (
            session.query(RfqLineItems.rfq_line_id)
            .filter(
                RfqLineItems.sys_rfq_id == sys_rfq_id,
                RfqLineItems.rfq_line_id.in_(rfq_line_ids)
            )
            .all()
        )
        valid_line_ids = {row[0] for row in valid_line_rows}
        invalid_line_ids = [rid for rid in rfq_line_ids if rid not in valid_line_ids]
        if invalid_line_ids:
            return jsonify({
                "status": False,
                "message": "Invalid rfq_line_ids for provided sys_rfq_id",
                "invalid_rfq_line_ids": invalid_line_ids
            }), 400

        existing = session.query(SupplierQuotation).filter_by(
            sys_rfq_id=sys_rfq_id,
            supplier_name=supplier_name
        ).first()

        if existing:
            existing_lines = (
                session.query(SupplierQuotationLineItem.rfq_line_id)
                .filter(SupplierQuotationLineItem.supplier_quotation_id == existing.supplier_quotation_id)
                .all()
            )
            return jsonify({
                "status": True,
                "message": "Supplier quotation already exists",
                "data": {
                    "supplier_quotation_id": existing.supplier_quotation_id,
                    "sys_rfq_id": sys_rfq_id,
                    "linked_line_items": [r[0] for r in existing_lines if r[0]]
                }
            }), 200

        # 🔹 Create header
        quotation = SupplierQuotation(
            sys_rfq_id=sys_rfq_id,
            supplier_name=supplier_name,
            supplier_email=data.get("supplier_email"),
            supplier_country=data.get("supplier_country"),
            supplier_currency=data.get("supplier_currency"),
            exchange_rate=data.get("exchange_rate"),
            status=data.get("status", "Pending"),
            remarks=data.get("remarks")
        )

        session.add(quotation)
        session.flush()  # get supplier_quotation_id

        # 🔹 Create reference-only line items
        for rfq_line_id in rfq_line_ids:
            line = SupplierQuotationLineItem(
                supplier_quotation_id=quotation.supplier_quotation_id,
                rfq_line_id=rfq_line_id
            )
            session.add(line)

        session.commit()

        return jsonify({
            "status": True,
            "message": "Supplier quotation created successfully",
            "data": {
                "supplier_quotation_id": quotation.supplier_quotation_id,
                "sys_rfq_id": sys_rfq_id,
                "linked_line_items": rfq_line_ids
            }
        }), 201

    except IntegrityError as e:
        session.rollback()
        return jsonify({
            "status": False,
            "message": "Invalid supplier quotation payload",
            "error": str(e.orig) if getattr(e, "orig", None) else str(e)
        }), 400
    except Exception as e:
        session.rollback()
        return jsonify({
            "status": False,
            "message": str(e)
        }), 500
    finally:
        session.close()

@supplier_bp.route("/quotation/<supplier_quotation_id>", methods=["GET"])
def get_supplier_quotation(supplier_quotation_id):
    session = next(db_session())
    try:
        quotation = session.query(SupplierQuotation).get(supplier_quotation_id)
        if not quotation:
            return jsonify({"status": False, "message": "Quotation not found"}), 404

        items = (
            session.query(SupplierQuotationLineItem, RfqLineItems)
            .join(RfqLineItems, SupplierQuotationLineItem.rfq_line_id == RfqLineItems.rfq_line_id)
            .filter(SupplierQuotationLineItem.supplier_quotation_id == supplier_quotation_id)
            .all()
        )

        return jsonify({
            "status": True,
            "data": {
                "supplier_quotation_id": quotation.supplier_quotation_id,
                "sys_rfq_id": quotation.sys_rfq_id,
                "supplier_name": quotation.supplier_name,
                "supplier_email": quotation.supplier_email,
                "supplier_country": quotation.supplier_country,
                "supplier_currency": quotation.supplier_currency,
                "exchange_rate": float(quotation.exchange_rate) if quotation.exchange_rate else None,
                "status": quotation.status,
                "remarks": quotation.remarks,
                "quotation_file_path": quotation.quotation_file_path,
                "local_delivery_partner": quotation.local_delivery_partner,
                "local_delivery_partner_type": quotation.local_delivery_partner_type,
                "freight_delivery_partner": quotation.freight_delivery_partner,
                "freight_delivery_partner_type": quotation.freight_delivery_partner_type,
                "accessible_dangerous_goods": quotation.accessible_dangerous_goods,
                "is_finalized": quotation.is_finalized,
                "finalized_at": quotation.finalized_at,
                "created_at": quotation.created_at,
                "updated_at": quotation.updated_at,
                "line_items": [
                    {
                        # RFQ Line Details
                        "rfq_line_id": rfq.rfq_line_id,
                        "customer_part_number": rfq.customer_part_number,
                        "product_description": rfq.product_description,
                        "quantity": float(rfq.quantity) if rfq.quantity else None,
                        "uom": rfq.uom,
                        "lead_time_days_required": rfq.lead_time_days,
                        "remarks": rfq.remarks,
                        # 🔥 QUESTION VALUES (from mapping_json)
                        "questions": rfq.mapping_json if rfq.mapping_json else {},
                        # Supplier's Quotation Response
                        "offered_quantity": float(item.offered_quantity) if item.offered_quantity else None,
                        "price_per_unit": float(item.price_per_unit) if item.price_per_unit else None,
                        "lead_time": item.lead_time,
                        "hsn_code": item.hsn_code,
                        "weight_of_package": item.weight_of_package,
                        "dim_of_package": item.dim_of_package,
                        "is_selected": item.is_selected,
                        "finalized_quantity": float(item.finalized_quantity) if item.finalized_quantity else None,
                        "supplier_line_item_id": item.supplier_line_item_id,
                        "created_at": item.created_at,
                        "updated_at": item.updated_at
                    }
                    for item, rfq in items
                ]
            }
        }), 200
    finally:
        session.close()

@supplier_bp.route("/quotation/update-by-rfq", methods=["POST"])
def update_supplier_quotation_by_rfq():
    session = next(db_session())
    try:
        data = request.get_json() or {}

        sys_rfq_id = data.get("sys_rfq_id")
        supplier_name = data.get("supplier_name")

        if not sys_rfq_id or not supplier_name:
            return jsonify({
                "status": False,
                "message": "sys_rfq_id and supplier_name are required"
            }), 400

        # 🔹 Find supplier quotation
        quotation = (
            session.query(SupplierQuotation)
            .filter(
                SupplierQuotation.sys_rfq_id == sys_rfq_id,
                SupplierQuotation.supplier_name == supplier_name
            )
            .one_or_none()
        )

        if not quotation:
            return jsonify({
                "status": False,
                "message": "Supplier quotation not found"
            }), 404

        # 🔹 Add header info ONLY if empty
        header = data.get("header", {})
        for field in [
            "supplier_email",
            "supplier_country",
            "customer_rfq_number",
            "quotation_file_path",
            "local_delivery_partner",
            "local_delivery_partner_type",
            "freight_delivery_partner",
            "freight_delivery_partner_type",
            "accessible_dangerous_goods"
        ]:
            if field in header and getattr(quotation, field) is None:
                setattr(quotation, field, header[field])
                
        processed_rfq_lines = set()

        # 🔹 Update ONLY specified line items
        for item in data.get("line_items", []):
            rfq_line_id = item.get("rfq_line_id")
            if not rfq_line_id:
                continue
            
            # 🚫 Skip invalid or duplicate RFQ lines
            if not rfq_line_id or rfq_line_id in processed_rfq_lines:
                continue

            processed_rfq_lines.add(rfq_line_id)

            line = (
                session.query(SupplierQuotationLineItem)
                .join(SupplierQuotation)
                .filter(
                    SupplierQuotation.sys_rfq_id == sys_rfq_id,
                    SupplierQuotation.supplier_name == supplier_name,
                    SupplierQuotationLineItem.rfq_line_id == rfq_line_id
                )
                .one_or_none()
            )

            if not line:
                continue

            for field in [
                "offered_quantity",
                "price_per_unit",
                "lead_time",
                "hsn_code",
                "weight_of_package",
                "dim_of_package"
            ]:
                if field in item:
                    setattr(line, field, item[field])

        # 🔹 Optional status update
        quotation.status = "Received"

        session.commit()

        return jsonify({
            "status": True,
            "message": "Supplier quotation updated successfully"
        }), 200

    except Exception as e:
        session.rollback()
        return jsonify({
            "status": False,
            "message": str(e)
        }), 500
    finally:
        session.close()



@supplier_bp.route("/quotation/by-rfq/<sys_rfq_id>", methods=["GET"])
def get_supplier_quotations_by_rfq(sys_rfq_id):
    session = next(db_session())
    try:
        quotations = (
            session.query(SupplierQuotation)
            .filter(
                SupplierQuotation.sys_rfq_id == sys_rfq_id
            )
            .all()
        )

        if not quotations:
            return jsonify({
                "status": False,
                "message": "No supplier quotations found for this RFQ"
            }), 404

        return jsonify({
            "status": True,
            "data": [
                {
                    "supplier_quotation_id": q.supplier_quotation_id,
                    "sys_rfq_id": q.sys_rfq_id,
                    "supplier_name": q.supplier_name,
                    "supplier_email": q.supplier_email,
                    "supplier_country": q.supplier_country,
                    "customer_rfq_number": q.customer_rfq_number,
                    "supplier_currency": q.supplier_currency,
                    "exchange_rate": float(q.exchange_rate) if q.exchange_rate else None,
                    "local_delivery_partner": q.local_delivery_partner,
                    "local_delivery_partner_type": q.local_delivery_partner_type,
                    "freight_delivery_partner": q.freight_delivery_partner,
                    "freight_delivery_partner_type": q.freight_delivery_partner_type,
                    "accessible_dangerous_goods": q.accessible_dangerous_goods,
                    "status": q.status,
                    "remarks": q.remarks,
                    "quotation_file_path": q.quotation_file_path,
                    "created_at": q.created_at,
                    "updated_at": q.updated_at
                }
                for q in quotations
            ]
        }), 200

    finally:
        session.close()


@supplier_bp.route("/quotation/details-by-rfq/<sys_rfq_id>", methods=["GET"])
def get_supplier_quotation_details_by_rfq(sys_rfq_id):
    """
    Unified RFQ-wise supplier quotation endpoint.
    Combines new flow (supplier_quotations_new) + legacy flow (supplier_quotations)
    so frontend can always render Supplier Quotations section.
    """
    session = next(db_session())
    try:
        rfq_key_norm = (sys_rfq_id or "").strip().lower()

        # New flow records
        new_rows = (
            session.query(SupplierQuotation)
            .filter(
                or_(
                    func.lower(func.trim(SupplierQuotation.sys_rfq_id)) == rfq_key_norm,
                    func.lower(func.trim(SupplierQuotation.customer_rfq_number)) == rfq_key_norm,
                )
            )
            .all()
        )

        new_data = [
            {
                "supplier_quotation_id": q.supplier_quotation_id,
                "sys_rfq_id": q.sys_rfq_id,
                "supplier_name": q.supplier_name,
                "supplier_email": q.supplier_email,
                "supplier_country": q.supplier_country,
                "supplier_currency": q.supplier_currency,
                "status": q.status,
                "remarks": q.remarks,
                "quotation_file_path": q.quotation_file_path,
                "created_at": q.created_at,
                "updated_at": q.updated_at,
                "source_table": "supplier_quotations_new",
            }
            for q in new_rows
        ]

        # Legacy flow records
        legacy_rows = (
            session.query(SupplierQuotations)
            .filter(func.lower(func.trim(SupplierQuotations.rfq_no)) == rfq_key_norm)
            .all()
        )

        legacy_data = [
            {
                "supplier_quotation_id": str(q.id),
                "sys_rfq_id": q.rfq_no,
                "supplier_name": q.supplier_name,
                "supplier_email": q.supplier_email,
                "supplier_country": None,
                "supplier_currency": q.currency,
                "status": q.status,
                "remarks": q.remarks,
                "quotation_file_path": q.quotation_file_path,
                "created_at": q.last_updated,
                "updated_at": q.last_updated,
                "source_table": "supplier_quotations",
            }
            for q in legacy_rows
        ]

        data = new_data if new_data else legacy_data

        return jsonify({
            "status": True,
            "status_code": 200,
            "message": "Supplier quotation details fetched successfully",
            "data": data,
        }), 200
    except Exception as e:
        return jsonify({
            "status": False,
            "status_code": 500,
            "message": "Failed to fetch supplier quotation details",
            "error": str(e),
        }), 500
    finally:
        session.close()


@supplier_bp.route("/quotation/fetch-all-by-rfq/<sys_rfq_id>", methods=["GET"])
def fetch_all_rfq_supplier_data(sys_rfq_id):
    session = next(db_session())
    try:
        rfq_key_norm = (sys_rfq_id or "").strip().lower()

        rfq = (
            session.query(RfqHeader)
            .filter(func.lower(func.trim(RfqHeader.sys_rfq_id)) == rfq_key_norm)
            .first()
        )

        if not rfq:
            return jsonify({
                "status": False,
                "message": "RFQ not found",
                "data": {}
            }), 404

        rfq_data = {
            "sys_rfq_id": rfq.sys_rfq_id,
            "customer_rfq_number": rfq.customer_rfq_number,
            "customer_company_name": rfq.customer_company_name,
            "customer_name": rfq.customer_name,
            "customer_email": rfq.customer_email,
            "rfq_date": rfq.rfq_date.isoformat() if rfq.rfq_date else None,
            "due_date": rfq.due_date.isoformat() if rfq.due_date else None,
            "currency": rfq.currency,
            "delivery_address": rfq.delivery_address,
            "delivery_country": rfq.delivery_country,
            "delivery_pincode": rfq.delivery_pincode,
            "notes": rfq.notes,
            "status": rfq.status,
            "finalized_quotation_json": rfq.finalized_quotation_json,
            "finalized_at": rfq.finalized_at.isoformat() if rfq.finalized_at else None,
            "created_at": rfq.created_at.isoformat() if rfq.created_at else None,
            "updated_at": rfq.updated_at.isoformat() if rfq.updated_at else None,
        }

        rfq_line_items = [
            {
                "rfq_line_id": item.rfq_line_id,
                "customer_part_number": item.customer_part_number,
                "product_description": item.product_description,
                "quantity": float(item.quantity) if item.quantity is not None else None,
                "uom": item.uom,
                "lead_time_days": item.lead_time_days,
                "remarks": item.remarks,
                "mapping_json": item.mapping_json,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in (
                session.query(RfqLineItems)
                .filter(RfqLineItems.sys_rfq_id == rfq.sys_rfq_id)
                .order_by(RfqLineItems.created_at)
                .all()
            )
        ]

        supplier_quotations = []
        quotations = (
            session.query(SupplierQuotation)
            .filter(func.lower(func.trim(SupplierQuotation.sys_rfq_id)) == rfq_key_norm)
            .order_by(SupplierQuotation.created_at)
            .all()
        )

        for quotation in quotations:
            charges = session.query(SupplierChargesCalculation).filter_by(
                supplier_quotation_id=quotation.supplier_quotation_id
            ).first()

            supplier_quotations.append({
                "supplier_quotation_id": quotation.supplier_quotation_id,
                "sys_rfq_id": quotation.sys_rfq_id,
                "supplier_name": quotation.supplier_name,
                "supplier_email": quotation.supplier_email,
                "supplier_country": quotation.supplier_country,
                "customer_rfq_number": quotation.customer_rfq_number,
                "supplier_currency": quotation.supplier_currency,
                "exchange_rate": float(quotation.exchange_rate) if quotation.exchange_rate is not None else None,
                "local_delivery_partner": quotation.local_delivery_partner,
                "local_delivery_partner_type": quotation.local_delivery_partner_type,
                "freight_delivery_partner": quotation.freight_delivery_partner,
                "freight_delivery_partner_type": quotation.freight_delivery_partner_type,
                "accessible_dangerous_goods": quotation.accessible_dangerous_goods,
                "status": quotation.status,
                "remarks": quotation.remarks,
                "quotation_file_path": quotation.quotation_file_path,
                "is_finalized": quotation.is_finalized,
                "finalized_at": quotation.finalized_at.isoformat() if quotation.finalized_at else None,
                "finalized_json": quotation.finalized_json,
                "created_at": quotation.created_at.isoformat() if quotation.created_at else None,
                "updated_at": quotation.updated_at.isoformat() if quotation.updated_at else None,
                "charges_calculation": charges.charges_json if charges else None,
                "line_items": [
                    {
                        "supplier_line_item_id": item.supplier_line_item_id,
                        "rfq_line_id": item.rfq_line_id,
                        "material_no": item.material_no,
                        "material_description": item.material_description,
                        "offered_quantity": float(item.offered_quantity) if item.offered_quantity is not None else None,
                        "price_per_unit": float(item.price_per_unit) if item.price_per_unit is not None else None,
                        "lead_time": item.lead_time,
                        "hsn_code": item.hsn_code,
                        "weight_of_package": item.weight_of_package,
                        "dim_of_package": item.dim_of_package,
                        "is_selected": item.is_selected,
                        "finalized_quantity": float(item.finalized_quantity) if item.finalized_quantity is not None else None,
                        "created_at": item.created_at.isoformat() if item.created_at else None,
                        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                    }
                    for item in quotation.line_items
                ]
            })

        return jsonify({
            "status": True,
            "message": "RFQ and supplier quotation data fetched successfully",
            "data": {
                "rfq_header": rfq_data,
                "rfq_line_items": rfq_line_items,
                "supplier_quotations": supplier_quotations,
            }
        }), 200

    except Exception as e:
        logger.exception("Failed to fetch RFQ and supplier quotation data")
        return jsonify({
            "status": False,
            "message": "Failed to fetch RFQ and supplier quotation data",
            "error": str(e)
        }), 500

    finally:
        session.close()


@supplier_bp.route("/quotation/counts/<sys_rfq_id>", methods=["GET"])
def get_supplier_quotation_counts(sys_rfq_id):
    """
    Returns RFQ-wise quotation progress for RFQ Management page.
    Example display: 5/10 (received/total)
    """
    session = next(db_session())
    try:
        rfq_key = (sys_rfq_id or "").strip()
        rfq_key_norm = rfq_key.lower()

        # New flow table: supplier_quotations_new
        new_total_count = (
            session.query(func.count(SupplierQuotation.supplier_quotation_id))
            .filter(
                or_(
                    func.lower(func.trim(SupplierQuotation.sys_rfq_id)) == rfq_key_norm,
                    func.lower(func.trim(SupplierQuotation.customer_rfq_number)) == rfq_key_norm,
                )
            )
            .scalar()
        ) or 0

        new_received_count = (
            session.query(func.count(SupplierQuotation.supplier_quotation_id))
            .filter(
                or_(
                    func.lower(func.trim(SupplierQuotation.sys_rfq_id)) == rfq_key_norm,
                    func.lower(func.trim(SupplierQuotation.customer_rfq_number)) == rfq_key_norm,
                ),
                or_(
                    func.lower(func.trim(SupplierQuotation.status)) == "received",
                    SupplierQuotation.quotation_file_path.isnot(None),
                ),
            )
            .scalar()
        ) or 0

        # If quotation_file_path has empty string values, exclude them from received.
        if new_received_count:
            new_received_count = (
                session.query(func.count(SupplierQuotation.supplier_quotation_id))
                .filter(
                    or_(
                        func.lower(func.trim(SupplierQuotation.sys_rfq_id)) == rfq_key_norm,
                        func.lower(func.trim(SupplierQuotation.customer_rfq_number)) == rfq_key_norm,
                    ),
                    or_(
                        func.lower(func.trim(SupplierQuotation.status)) == "received",
                        func.length(func.trim(SupplierQuotation.quotation_file_path)) > 0,
                    ),
                )
                .scalar()
            ) or 0

        # Legacy flow table: supplier_quotations
        legacy_total_count = (
            session.query(func.count(SupplierQuotations.id))
            .filter(func.lower(func.trim(SupplierQuotations.rfq_no)) == rfq_key_norm)
            .scalar()
        ) or 0

        legacy_received_count = (
            session.query(func.count(SupplierQuotations.id))
            .filter(
                func.lower(func.trim(SupplierQuotations.rfq_no)) == rfq_key_norm,
                or_(
                    func.lower(func.trim(SupplierQuotations.status)) == "received",
                    func.length(func.trim(SupplierQuotations.quotation_file_path)) > 0,
                ),
            )
            .scalar()
        ) or 0

        # Use whichever flow has data for this RFQ.
        if new_total_count > 0:
            total_count = new_total_count
            received_count = new_received_count
            source_table = "supplier_quotations_new"
        elif legacy_total_count > 0:
            total_count = legacy_total_count
            received_count = legacy_received_count
            source_table = "supplier_quotations"
        else:
            total_count = 0
            received_count = 0
            source_table = "none"

        return jsonify({
            "status": True,
            "status_code": 200,
            "message": "Supplier quotation counts fetched successfully",
            "data": {
                "sys_rfq_id": sys_rfq_id,
                "received_count": int(received_count),
                "total_count": int(total_count),
                "display_count": f"{int(received_count)}/{int(total_count)}",
                "source_table": source_table
            }
        }), 200
    except Exception as e:
        return jsonify({
            "status": False,
            "status_code": 500,
            "message": "Failed to fetch supplier quotation counts",
            "error": str(e)
        }), 500
    finally:
        session.close()






# utils_normalization.p
def parse_decimal(value):
    """
    Converts:
    'INR 1,200.50', '1,200.50', '1200.50', 1200, 1200.5 → Decimal
    """
    if value is None:
        return None

    if isinstance(value, Decimal):
        return value

    if isinstance(value, (int, float)):
        return Decimal(str(value))

    s = str(value)

    # 🔥 KEY FIX: remove commas BEFORE parsing
    s = s.replace(",", "")

    match = re.search(r"\d+(\.\d+)?", s)
    if not match:
        return None

    try:
        return Decimal(match.group())
    except Exception:
        return None

def parse_quantity(value):
    """
    Converts:
    '16 Nos', '16', 16 → Decimal
    """
    return parse_decimal(value)


def normalize_string(s):
    """Normalize string for comparison: uppercase, no spaces, no hyphens"""
    if not s:
        return ""
    return str(s).strip().upper().replace(" ", "").replace("-", "")


def normalize_boolean(value):
    """Convert string boolean to actual boolean"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ["true", "1", "yes", "y"]
    return False


def get_first_present(d: dict, *keys):
    """
    Returns the first non-null value from a dict for given keys.
    Supports LLM aliases safely.
    """
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None



# def normalize_string(s):
#     """Normalize string for comparison: uppercase, no spaces"""
#     if not s:
#         return ""
#     return str(s).strip().upper().replace(" ", "").replace("-", "")


# def normalize_boolean(value):
#     """Convert string boolean to actual boolean"""
#     if isinstance(value, bool):
#         return value
#     if isinstance(value, str):
#         return value.lower() in ['true', '1', 'yes', 'y']
#     return False

def find_supplier_quotation(session, rfq_id, supplier_name, supplier_email=None):
    all_quotations = (
        session.query(SupplierQuotation)
        .filter(SupplierQuotation.sys_rfq_id == rfq_id)
        .all()
    )

    if not all_quotations:
        return None, {"error": "No quotations found for this RFQ"}

    # 1. Exact email match
    if supplier_email:
        for quotation in all_quotations:
            if quotation.supplier_email and quotation.supplier_email.lower().strip() == supplier_email.lower().strip():
                return quotation, {
                    "method": "exact_email",
                    "confidence": 100,
                    "matched_name": quotation.supplier_name
                }

    # 2. Exact name match
    for quotation in all_quotations:
        if quotation.supplier_name.lower().strip() == supplier_name.lower().strip():
            return quotation, {
                "method": "exact_name",
                "confidence": 100,
                "matched_name": quotation.supplier_name
            }

    # 3. Fuzzy match
    supplier_names = [q.supplier_name for q in all_quotations]
    best_match = process.extractOne(supplier_name, supplier_names, scorer=fuzz.token_sort_ratio)

    if best_match:
        name, score, index = best_match
        if score >= 85:
            return all_quotations[index], {
                "method": "fuzzy_name",
                "confidence": score,
                "matched_name": name
            }

    return None, {"error": "No matching supplier found"}

# def build_material_mapping(session, rfq_id):
#     """
#     Build mapping from RFQ line items to enable material matching.
    
#     Returns:
#         dict with:
#         - manufacturer_part_map: normalized manufacturer part -> rfq_line_id
#         - customer_part_map: normalized customer part -> rfq_line_id
#         - description_map: product description -> rfq_line_id
#         - duplicate_parts: dict of duplicate manufacturer parts (for warnings)
#     """
#     rfq_lines = (
#         session.query(RfqLineItems)
#         .filter(
#             RfqLineItems.sys_rfq_id == rfq_id,
#             RfqLineItems.deleted_flag == False
#         )
#         .all()
#     )

#     if not rfq_lines:
#         logger.warning(f"No RFQ line items found for {rfq_id}")
#         return {
#             "manufacturer_part_map": {},
#             "customer_part_map": {},
#             "description_map": {},
#             "duplicate_parts": {}
#         }

#     manufacturer_part_map = {}
#     customer_part_map = {}
#     description_map = {}
#     duplicate_parts = {}  # Track duplicate manufacturer parts

#     for line in rfq_lines:
#         # Customer part number mapping
#         if line.customer_part_number:
#             normalized_customer = normalize_string(line.customer_part_number)
#             if normalized_customer:
#                 customer_part_map[normalized_customer] = line.rfq_line_id

#         # Manufacturer part number mapping (from mapping_json)
#         if line.mapping_json:
#             if isinstance(line.mapping_json, list):
#                 for mapping in line.mapping_json:
#                     part = mapping.get("manufacturer_product_name")
#                     if part:
#                         normalized = normalize_string(part)
#                         if normalized:
#                             # Check for duplicates
#                             if normalized in manufacturer_part_map:
#                                 if normalized not in duplicate_parts:
#                                     duplicate_parts[normalized] = [manufacturer_part_map[normalized]]
#                                 duplicate_parts[normalized].append(line.rfq_line_id)
#                                 logger.warning(
#                                     f"Duplicate manufacturer part '{part}' found in RFQ {rfq_id}. "
#                                     f"Lines: {duplicate_parts[normalized]}"
#                                 )
#                             else:
#                                 manufacturer_part_map[normalized] = line.rfq_line_id
#             elif isinstance(line.mapping_json, dict):
#                 # Handle case where mapping_json is a single dict
#                 part = line.mapping_json.get("manufacturer_product_name")
#                 if part:
#                     normalized = normalize_string(part)
#                     if normalized:
#                         if normalized in manufacturer_part_map:
#                             if normalized not in duplicate_parts:
#                                 duplicate_parts[normalized] = [manufacturer_part_map[normalized]]
#                             duplicate_parts[normalized].append(line.rfq_line_id)
#                         else:
#                             manufacturer_part_map[normalized] = line.rfq_line_id

#         # Description mapping
#         if line.product_description:
#             description_map[line.product_description] = line.rfq_line_id

#     return {
#         "manufacturer_part_map": manufacturer_part_map,
#         "customer_part_map": customer_part_map,
#         "description_map": description_map,
#         "duplicate_parts": duplicate_parts
#     }


import json

def build_material_mapping(session, rfq_id):
    """
    Build mapping from RFQ line items to enable material matching.
    
    Returns:
        dict with:
        - manufacturer_part_map: normalized manufacturer part -> rfq_line_id
        - customer_part_map: normalized customer part -> rfq_line_id
        - description_map: product description -> rfq_line_id
        - duplicate_parts: dict of duplicate manufacturer parts (for warnings)
    """
    rfq_lines = (
        session.query(RfqLineItems)
        .filter(
            RfqLineItems.sys_rfq_id == rfq_id,
            RfqLineItems.deleted_flag == False
        )
        .all()
    )

    if not rfq_lines:
        logger.warning(f"No RFQ line items found for {rfq_id}")
        return {
            "manufacturer_part_map": {},
            "customer_part_map": {},
            "description_map": {},
            "duplicate_parts": {}
        }

    manufacturer_part_map = {}
    customer_part_map = {}
    description_map = {}
    rfq_line_id_map = {}  # Direct rfq_line_id mapping
    duplicate_parts = {}  # Track duplicate manufacturer parts

    for line in rfq_lines:
        # Direct rfq_line_id mapping (HIGHEST PRIORITY)
        if line.rfq_line_id:
            normalized_rfq_id = normalize_string(line.rfq_line_id)
            if normalized_rfq_id:
                rfq_line_id_map[normalized_rfq_id] = line.rfq_line_id
        # ------------------------------------------------------------
        # Customer part number mapping (UNCHANGED)
        # ------------------------------------------------------------
        if line.customer_part_number:
            normalized_customer = normalize_string(line.customer_part_number)
            if normalized_customer:
                customer_part_map[normalized_customer] = line.rfq_line_id

        # ------------------------------------------------------------
        # ADDITIVE NORMALIZATION ONLY (NO LOGIC CHANGE)
        # Handle mapping_json stored as STRING
        # ------------------------------------------------------------
        mapping_json = line.mapping_json
        if isinstance(mapping_json, str):
            try:
                mapping_json = json.loads(mapping_json)
            except Exception as e:
                logger.error(
                    f"Invalid mapping_json for RFQ line {line.rfq_line_id}: {e}"
                )
                mapping_json = None

        # ------------------------------------------------------------
        # Manufacturer part number mapping (CORE LOGIC UNCHANGED)
        # ------------------------------------------------------------
        if mapping_json:
            if isinstance(mapping_json, list):
                for mapping in mapping_json:
                    part = mapping.get("manufacturer_product_name")
                    if part:
                        normalized = normalize_string(part)
                        if normalized:
                            # Check for duplicates
                            if normalized in manufacturer_part_map:
                                if normalized not in duplicate_parts:
                                    duplicate_parts[normalized] = [
                                        manufacturer_part_map[normalized]
                                    ]
                                duplicate_parts[normalized].append(line.rfq_line_id)
                                logger.warning(
                                    f"Duplicate manufacturer part '{part}' found in RFQ {rfq_id}. "
                                    f"Lines: {duplicate_parts[normalized]}"
                                )
                            else:
                                manufacturer_part_map[normalized] = line.rfq_line_id

            elif isinstance(mapping_json, dict):
                # Handle case where mapping_json is a single dict
                part = mapping_json.get("manufacturer_product_name")
                if part:
                    normalized = normalize_string(part)
                    if normalized:
                        if normalized in manufacturer_part_map:
                            if normalized not in duplicate_parts:
                                duplicate_parts[normalized] = [
                                    manufacturer_part_map[normalized]
                                ]
                            duplicate_parts[normalized].append(line.rfq_line_id)
                        else:
                            manufacturer_part_map[normalized] = line.rfq_line_id

        # ------------------------------------------------------------
        # Description mapping (UNCHANGED)
        # ------------------------------------------------------------
        if line.product_description:
            description_map[line.product_description] = line.rfq_line_id

    return {
        "rfq_line_id_map": rfq_line_id_map,
        "manufacturer_part_map": manufacturer_part_map,
        "customer_part_map": customer_part_map,
        "description_map": description_map,
        "duplicate_parts": duplicate_parts
    }


def match_material_to_rfq_line(material, mapping_data):
    """
    Match a single supplier material to an RFQ line item
    
    Args:
        material: dict with supplier's material data
        mapping_data: dict from build_material_mapping()
    
    Returns:
        tuple: (rfq_line_id or None, match_info dict)
    """
    material_no = material.get('material_no', '')
    material_desc = material.get('material_description', '')
    
    normalized_material_no = normalize_string(material_no)
    
    match_info = {
        'material_no': material_no,
        'method': None,
        'confidence': 0,
        'rfq_line_id': None
    }
    
    # Strategy 0: Direct rfq_line_id match (HIGHEST PRIORITY)
    if normalized_material_no in mapping_data.get('rfq_line_id_map', {}):
        match_info['rfq_line_id'] = mapping_data['rfq_line_id_map'][normalized_material_no]
        match_info['method'] = 'rfq_line_id_exact'
        match_info['confidence'] = 100
        return match_info['rfq_line_id'], match_info
    
    # Strategy 1: Manufacturer part number
    if normalized_material_no in mapping_data['manufacturer_part_map']:
        match_info['rfq_line_id'] = mapping_data['manufacturer_part_map'][normalized_material_no]
        match_info['method'] = 'manufacturer_part_exact'
        match_info['confidence'] = 100
        return match_info['rfq_line_id'], match_info
    
    # Strategy 2: Customer part number
    if normalized_material_no in mapping_data['customer_part_map']:
        match_info['rfq_line_id'] = mapping_data['customer_part_map'][normalized_material_no]
        match_info['method'] = 'customer_part_exact'
        match_info['confidence'] = 95
        return match_info['rfq_line_id'], match_info
    
    # Strategy 3: Fuzzy match on description (LOWEST PRIORITY)
    if material_desc and mapping_data['description_map']:
        best_match = process.extractOne(
            material_desc,
            list(mapping_data['description_map'].keys()),
            scorer=fuzz.token_sort_ratio
        )
        
        if best_match and best_match[1] >= 80:  # 80% threshold for descriptions
            matched_desc = best_match[0]
            match_info['rfq_line_id'] = mapping_data['description_map'][matched_desc]
            match_info['method'] = 'description_fuzzy'
            match_info['confidence'] = best_match[1]
            match_info['matched_description'] = matched_desc
            return match_info['rfq_line_id'], match_info
    
    # No match found
    match_info['method'] = 'no_match'
    match_info['reason'] = 'Material not found in RFQ line items'
    return None, match_info



# @supplier_bp.route("/supplier-quotation/update", methods=["POST"])
# def update_supplier_quotation():
#     session = next(db_session())

#     try:
#         data = request.get_json()
#         if not data:
#             return jsonify({"success": False, "error": "No JSON data provided"}), 400

#         # ------------------------------------------------------------------
#         # ADDITIVE FIX #1: ROOT-LEVEL PAYLOAD SUPPORT (NO LOGIC CHANGE)
#         # ------------------------------------------------------------------
#         sys_rfq_id = data.get("sys_rfq_id") or data.get("rfq_no")
#         if not sys_rfq_id:
#             return jsonify({"success": False, "error": "sys_rfq_id or rfq_no is required"}), 400

#         supplier_name = data.get("supplier_name")
#         supplier_email = data.get("supplier_email")

#         if not supplier_name:
#             return jsonify({"success": False, "error": "supplier_name is required"}), 400

#         # ------------------------------------------------------------------
#         # EXISTING CORE LOGIC (UNCHANGED)
#         # ------------------------------------------------------------------
#         quotation, supplier_match_info = find_supplier_quotation(
#             session,
#             sys_rfq_id,
#             supplier_name,
#             supplier_email
#         )

#         if not quotation:
#             return jsonify({
#                 "success": False,
#                 "error": "Supplier quotation not found",
#                 "match_info": supplier_match_info
#             }), 404

#         mapping_data = build_material_mapping(session, sys_rfq_id)

#         # ------------------------------------------------------------------
#         # HEADER UPDATE (UNCHANGED LOGIC, ONLY SAFE NORMALIZATION)
#         # ------------------------------------------------------------------
#         quotation.supplier_currency = data.get("currency")
#         quotation.exchange_rate = data.get("exchange_rate")
#         quotation.supplier_country = data.get("supplier_country")
#         quotation.accessible_dangerous_goods = normalize_boolean(
#             data.get("accessible_dangerous_goods")
#         )
#         quotation.status = "Received"
#         quotation.remarks = data.get("remarks", "Updated from email")
#         quotation.local_delivery_partner = data.get("local_delivery_partner")or None
#         quotation.local_delivery_partner_type = data.get("local_delivery_partner_type") or None
#         quotation.freight_delivery_partner = data.get("freight_delivery_partner") or None
#         quotation.freight_delivery_partner_type = data.get("freight_delivery_partner_type") or None
#         quotation.updated_at = datetime.utcnow()

#         if supplier_email and not quotation.supplier_email:
#             quotation.supplier_email = supplier_email

#         # ------------------------------------------------------------------
#         # MATERIALS (CORE FLOW UNCHANGED)
#         # ------------------------------------------------------------------
#         materials = data.get("materials", [])
#         if not materials:
#             return jsonify({"success": False, "error": "materials are required"}), 400

#         updated_lines = []
#         created_lines = []
#         unmatched_materials = []
#         failed_materials = []
#         match_details = []

#         for material in materials:
#             material_no = material.get("material_no")
#             if not material_no:
#                 continue

#             rfq_line_id = None
#             match_info = None

#             try:
#                 # ----------------------------------------------------------
#                 # EXISTING MATCHING LOGIC (UNCHANGED)
#                 # ----------------------------------------------------------
#                 rfq_line_id, match_info = match_material_to_rfq_line(
#                     material, mapping_data
#                 )
#                 match_details.append(match_info)

#                 if not rfq_line_id:
#                     unmatched_materials.append({
#                         "material_no": material_no,
#                         "material_description": material.get("material_description"),
#                         "match_info": match_info
#                     })
#                     continue

#                 supplier_line = (
#                     session.query(SupplierQuotationLineItem)
#                     .filter_by(
#                         supplier_quotation_id=quotation.supplier_quotation_id,
#                         rfq_line_id=rfq_line_id
#                     )
#                     .first()
#                 )

#                 # ----------------------------------------------------------
#                 # ADDITIVE FIX #2: LLM FIELD ALIASES + NORMALIZATION
#                 # ----------------------------------------------------------
#                 offered_qty = parse_quantity(
#                     get_first_present(material, "offered_quantity")
#                 )

#                 price_per_unit = parse_decimal(
#                     get_first_present(material, "price_per_unit", "unit_price")
#                 )

#                 lead_time = get_first_present(
#                     material, "lead_time", "lead_time_days"
#                 )

#                 if supplier_line:
#                     supplier_line.rfq_line_id = rfq_line_id
#                     supplier_line.material_no = material_no
#                     supplier_line.material_description = material.get("material_description")
#                     supplier_line.offered_quantity = offered_qty
#                     supplier_line.price_per_unit = price_per_unit
#                     supplier_line.lead_time = lead_time
#                     supplier_line.hsn_code = material.get("hsn_code")
#                     supplier_line.weight_of_package = material.get("weight_of_package")
#                     supplier_line.dim_of_package = material.get("dim_of_package")
#                     supplier_line.updated_at = datetime.utcnow()

#                     updated_lines.append({
#                         "material_no": material_no,
#                         "rfq_line_id": rfq_line_id,
#                         "match_method": match_info.get("method"),
#                         "confidence": match_info.get("confidence")
#                     })

#                 else:
#                     new_line = SupplierQuotationLineItem(
#                         supplier_quotation_id=quotation.supplier_quotation_id,
#                         rfq_line_id=rfq_line_id,
#                         material_no=material_no,
#                         material_description=material.get("material_description"),
#                         offered_quantity=offered_qty,
#                         price_per_unit=price_per_unit,
#                         lead_time=lead_time,
#                         hsn_code=material.get("hsn_code"),
#                         weight_of_package=material.get("weight_of_package"),
#                         dim_of_package=material.get("dim_of_package")
#                     )
#                     session.add(new_line)
#                     session.flush()

#                     created_lines.append({
#                         "material_no": material_no,
#                         "rfq_line_id": rfq_line_id,
#                         "match_method": match_info.get("method"),
#                         "confidence": match_info.get("confidence")
#                     })

#             except Exception as material_error:
#                 session.rollback()
#                 failed_materials.append({
#                     "material_no": material_no,
#                     "error": str(material_error),
#                     "rfq_line_id": rfq_line_id
#                 })
#                 continue

#         # ------------------------------------------------------------------
#         # COMMIT (UNCHANGED)
#         # ------------------------------------------------------------------
#         session.commit()

#         return jsonify({
#             "success": True,
#             "supplier_matching": supplier_match_info,
#             "updated_lines": updated_lines,
#             "created_lines": created_lines,
#             "unmatched_materials": unmatched_materials,
#             "failed_materials": failed_materials,
#             "match_details": match_details
#         }), 200

#     except Exception as e:
#         session.rollback()
#         return jsonify({"success": False, "error": str(e)}), 500

#     finally:
#         session.close()



@supplier_bp.route("/supplier-quotation/update", methods=["POST"])
def update_supplier_quotation():
    session = next(db_session())

    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data provided"}), 400

        # ------------------------------------------------------------------
        # ADDITIVE FIX #1: ROOT-LEVEL PAYLOAD SUPPORT (NO LOGIC CHANGE)
        # ------------------------------------------------------------------
        sys_rfq_id = data.get("sys_rfq_id") or data.get("rfq_no")
        if not sys_rfq_id:
            return jsonify({"success": False, "error": "sys_rfq_id or rfq_no is required"}), 400

        supplier_name = data.get("supplier_name")
        supplier_email = data.get("supplier_email")

        if not supplier_name:
            return jsonify({"success": False, "error": "supplier_name is required"}), 400

        # ------------------------------------------------------------------
        # EXISTING CORE LOGIC (UNCHANGED)
        # ------------------------------------------------------------------
        quotation, supplier_match_info = find_supplier_quotation(
            session,
            sys_rfq_id,
            supplier_name,
            supplier_email
        )

        if not quotation:
            return jsonify({
                "success": False,
                "error": "Supplier quotation not found",
                "match_info": supplier_match_info
            }), 404

        mapping_data = build_material_mapping(session, sys_rfq_id)

        # ------------------------------------------------------------------
        # HEADER UPDATE (UNCHANGED LOGIC)
        # ------------------------------------------------------------------
        quotation.supplier_currency = data.get("currency")
        quotation.exchange_rate = data.get("exchange_rate")
        quotation.supplier_country = data.get("supplier_country")
        quotation.accessible_dangerous_goods = normalize_boolean(
            data.get("accessible_dangerous_goods")
        )
        quotation.status = "Received"
        quotation.remarks = data.get("remarks", "Updated from email")
        quotation.local_delivery_partner = data.get("local_delivery_partner") or None
        quotation.local_delivery_partner_type = data.get("local_delivery_partner_type") or None
        quotation.freight_delivery_partner = data.get("freight_delivery_partner") or None
        quotation.freight_delivery_partner_type = data.get("freight_delivery_partner_type") or None
        quotation.updated_at = datetime.utcnow()

        if supplier_email and not quotation.supplier_email:
            quotation.supplier_email = supplier_email

        # ------------------------------------------------------------------
        # MATERIALS (CORE FLOW UNCHANGED)
        # ------------------------------------------------------------------
        materials = data.get("materials", [])
        if not materials:
            return jsonify({"success": False, "error": "materials are required"}), 400

        updated_lines = []
        created_lines = []
        unmatched_materials = []
        failed_materials = []
        match_details = []

        for material in materials:
            # ✅ ADDITIVE: isolate each material
            with session.begin_nested():

                material_no = material.get("material_no")
                if not material_no:
                    continue

                rfq_line_id = None
                match_info = None

                try:
                    # ----------------------------------------------------------
                    # EXISTING MATCHING LOGIC (UNCHANGED)
                    # ----------------------------------------------------------
                    rfq_line_id, match_info = match_material_to_rfq_line(
                        material, mapping_data
                    )
                    match_details.append(match_info)

                    if not rfq_line_id:
                        unmatched_materials.append({
                            "material_no": material_no,
                            "material_description": material.get("material_description"),
                            "match_info": match_info
                        })
                        continue

                    supplier_line = (
                        session.query(SupplierQuotationLineItem)
                        .filter_by(
                            supplier_quotation_id=quotation.supplier_quotation_id,
                            rfq_line_id=rfq_line_id
                        )
                        .first()
                    )

                    # ----------------------------------------------------------
                    # ADDITIVE FIX #2: LLM FIELD ALIASES + NORMALIZATION
                    # ----------------------------------------------------------
                    offered_qty = parse_quantity(
                        get_first_present(material, "offered_quantity","required_quantity")
                    )

                    price_per_unit = parse_decimal(
                        get_first_present(material, "price_per_unit", "unit_price")
                    )

                    lead_time = get_first_present(
                        material,
                        "lead_time",
                        "lead_time_days",
                        "leadtime",
                        "leadTime",
                        "lead time",
                        "delivery_lead_time",
                        "deliveryLeadTime",
                    )
                    # Prevent blank payload values from wiping existing lead time.
                    if isinstance(lead_time, str):
                        lead_time = lead_time.strip() or None

                    weight_of_package = get_first_present(
                        material, "weight_of_package", "weight"
                    )

                    dim_of_package = get_first_present(
                        material, "dim_of_package", "dimensions"
                    )

                    logger.info(
                        "Processing material | material_no=%s | rfq_line_id=%s | offered_qty=%s",
                        material_no,
                        rfq_line_id,
                        offered_qty
                    )

                    if supplier_line:
                        supplier_line.rfq_line_id = rfq_line_id
                        supplier_line.material_no = material_no
                        supplier_line.material_description = material.get("material_description")
                        supplier_line.offered_quantity = offered_qty
                        supplier_line.price_per_unit = price_per_unit
                        supplier_line.lead_time = lead_time
                        supplier_line.hsn_code = material.get("hsn_code")
                        supplier_line.weight_of_package = weight_of_package
                        supplier_line.dim_of_package = dim_of_package
                        supplier_line.updated_at = datetime.utcnow()

                        logger.info(
                            "Updated supplier line | rfq_line_id=%s | offered_qty=%s",
                            rfq_line_id,
                            supplier_line.offered_quantity
                        )

                        updated_lines.append({
                            "material_no": material_no,
                            "rfq_line_id": rfq_line_id,
                            "match_method": match_info.get("method"),
                            "confidence": match_info.get("confidence")
                        })

                    else:
                        new_line = SupplierQuotationLineItem(
                            supplier_quotation_id=quotation.supplier_quotation_id,
                            rfq_line_id=rfq_line_id,
                            material_no=material_no,
                            material_description=material.get("material_description"),
                            offered_quantity=offered_qty,
                            price_per_unit=price_per_unit,
                            lead_time=lead_time,
                            hsn_code=material.get("hsn_code"),
                            weight_of_package=weight_of_package,
                            dim_of_package=dim_of_package
                        )
                        session.add(new_line)
                        session.flush()

                        logger.info(
                            "Created supplier line | rfq_line_id=%s | offered_qty=%s",
                            rfq_line_id,
                            offered_qty
                        )

                        created_lines.append({
                            "material_no": material_no,
                            "rfq_line_id": rfq_line_id,
                            "match_method": match_info.get("method"),
                            "confidence": match_info.get("confidence")
                        })

                except Exception as material_error:
                    # ❌ NO GLOBAL ROLLBACK HERE (CRITICAL FIX)
                    logger.exception(
                        "Material processing failed | material_no=%s | rfq_line_id=%s",
                        material_no,
                        rfq_line_id
                    )
                    failed_materials.append({
                        "material_no": material_no,
                        "error": str(material_error),
                        "rfq_line_id": rfq_line_id
                    })
                    continue

        # ------------------------------------------------------------------
        # COMMIT (UNCHANGED)
        # ------------------------------------------------------------------ ------------------------------------------------------------------
        # 🔹 CHARGES SAVE / UPDATE (ADD THIS BLOCK)
        # ------------------------------------------------------------------
        charges_data = data.get("charges_calculation")

        if charges_data:
            existing = session.query(SupplierChargesCalculation).filter_by(
                supplier_quotation_id=quotation.supplier_quotation_id
            ).first()

            if existing:
                existing.charges_json = charges_data
                existing.updated_at = datetime.utcnow()
                logger.info(
                    "Updated charges for quotation_id=%s",
                    quotation.supplier_quotation_id
                )
            else:
                new_charges = SupplierChargesCalculation(
                    supplier_quotation_id=quotation.supplier_quotation_id,
                    rfq_no=quotation.sys_rfq_id,
                    charges_json=charges_data
                )
                session.add(new_charges)

                logger.info(
                    "Created charges for quotation_id=%s",
                    quotation.supplier_quotation_id
                )
        logger.info(
            "Final commit | quotation_id=%s | updated=%d | created=%d | failed=%d",
            quotation.supplier_quotation_id,
            len(updated_lines),
            len(created_lines),
            len(failed_materials)
        )
        #    
        session.commit()

        return jsonify({
            "success": True,
            "supplier_matching": supplier_match_info,
            "updated_lines": updated_lines,
            "created_lines": created_lines,
            "unmatched_materials": unmatched_materials,
            "failed_materials": failed_materials,
            "match_details": match_details
        }), 200

       

      

    except Exception as e:
        session.rollback()
        logger.exception("Fatal supplier quotation update error")
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        session.close()

@supplier_bp.route("/charges/by-rfq/<rfq_no>", methods=["GET"])
def get_charges_by_rfq(rfq_no):
    session = next(db_session())
    try:
        charges = session.query(SupplierChargesCalculation).filter_by(rfq_no=rfq_no).all()
        result = [
            {
                "supplier_quotation_id": c.supplier_quotation_id,
                "rfq_no": c.rfq_no,
                "charges_calculation": c.charges_json,
                "created_at": c.created_at,
                "updated_at": c.updated_at
            }
            for c in charges
        ]
        return jsonify({"status": True, "data": result}), 200
    finally:
        session.close()
