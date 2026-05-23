from flask import Blueprint, request, jsonify
from datetime import datetime
from app.models.rfq_header import RfqHeader
from app.models.rfq_line_items import RfqLineItems
from app.database.DatabaseOperationPostgreSQL import db_session
import random
import re
from logging_config import setup_logging
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, case, or_, cast, String
from app.models import SupplierQuotation, SupplierQuotations
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
from sqlalchemy import text
from rapidfuzz import process, fuzz
logger = setup_logging("RfqWebhook_Routes", level="DEBUG")

rfq_webhook_blueprint = Blueprint("rfq/webhook/", __name__)



def generate_rfq_id(session):
    while True:
        new_id = f"RFQ_{random.randint(100000, 999999)}"
        exists = session.query(RfqHeader).filter_by(sys_rfq_id=new_id).first()
        if not exists:
            return new_id


def parse_due_date(date_str: str):
    if not date_str:
        return None

    cleaned = date_str.replace(" ", "")
    formats = [
        "%d.%m.%Y%H:%M:%S",
        "%d.%m.%Y",
        "%Y-%m-%d"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue

    return None


def safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_tracking_key(value: str) -> str:
    """Normalize tracking keys for resume lookup."""

    logger.info(
        "[TRACKING_KEY] Normalizing tracking key | raw_value=%s",
        value
    )

    normalized_value = str(value or "").strip().lower()

    logger.info(
        "[TRACKING_KEY] Normalized tracking key | normalized_value=%s",
        normalized_value
    )

    return normalized_value

def _find_wait_state_by_rfq(session, rfq_id: str):

    logger.info(
        "[WAIT_STATE] Start searching wait state | rfq_id=%s",
        rfq_id
    )

    normalized_rfq_key = _normalize_tracking_key(rfq_id)

    logger.info(
        "[WAIT_STATE] Normalized RFQ key | normalized_rfq_key='%s'",
        normalized_rfq_key
    )

    # --------------------------------------------------
    # DEBUG ALL WAITING TRACKING KEYS
    # --------------------------------------------------
    logger.info(
        "[WAIT_STATE] Fetching all waiting tracking keys for comparison"
    )

    waiting_rows = (
        session.query(
            WorkflowWaitState.id,
            WorkflowWaitState.workflow_run_id,
            WorkflowWaitState.tracking_key,
            WorkflowWaitState.status,
            func.lower(func.trim(WorkflowWaitState.tracking_key)).label("normalized_db_key"),
        )
        .filter(WorkflowWaitState.status == "waiting")
        .all()
    )

    logger.info(
        "[WAIT_STATE] Total waiting states found | count=%s",
        len(waiting_rows)
    )

    for row in waiting_rows:
        logger.info(
            "[WAIT_STATE COMPARE] "
            "wait_state_id=%s | "
            "workflow_run_id=%s | "
            "db_raw_key='%s' | "
            "db_normalized_key='%s' | "
            "input_normalized_key='%s' | "
            "matched=%s",
            row.id,
            row.workflow_run_id,
            row.tracking_key,
            row.normalized_db_key,
            normalized_rfq_key,
            row.normalized_db_key == normalized_rfq_key
        )

    # --------------------------------------------------
    # EXACT MATCH
    # --------------------------------------------------
    logger.info(
        "[WAIT_STATE] Trying exact match query"
    )

    wait_state = (
        session.query(WorkflowWaitState)
        .filter(
            func.lower(func.trim(WorkflowWaitState.tracking_key)) == normalized_rfq_key,
            WorkflowWaitState.status == "waiting",
        )
        .first()
    )

    if wait_state:

        logger.info(
            "[WAIT_STATE] Exact match found | wait_state_id=%s | workflow_run_id=%s | tracking_key='%s'",
            wait_state.id,
            wait_state.workflow_run_id,
            wait_state.tracking_key,
        )

        return wait_state

    logger.warning(
        "[WAIT_STATE] Exact match not found | rfq_id=%s",
        rfq_id
    )

    # --------------------------------------------------
    # PARTIAL MATCH
    # --------------------------------------------------
    escaped_rfq_key = (
        normalized_rfq_key
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )

    logger.info(
        "[WAIT_STATE] Trying partial match | escaped_rfq_key='%s'",
        escaped_rfq_key
    )

    partial_matches = (
        session.query(WorkflowWaitState)
        .filter(
            WorkflowWaitState.status == "waiting",
            func.lower(func.trim(WorkflowWaitState.tracking_key)).like(
                f"%{escaped_rfq_key}%",
                escape="\\"
            )
        )
        .all()
    )

    logger.info(
        "[WAIT_STATE] Partial match results | count=%s",
        len(partial_matches)
    )

    for match in partial_matches:
        logger.info(
            "[WAIT_STATE PARTIAL MATCH] "
            "wait_state_id=%s | "
            "workflow_run_id=%s | "
            "tracking_key='%s'",
            match.id,
            match.workflow_run_id,
            match.tracking_key
        )

    if len(partial_matches) == 1:

        logger.info(
            "[WAIT_STATE] Single partial match selected | wait_state_id=%s",
            partial_matches[0].id
        )

        return partial_matches[0]

    if partial_matches:

        logger.warning(
            "[WAIT_STATE] Multiple partial matches found | rfq_id=%s | count=%s",
            rfq_id,
            len(partial_matches),
        )

    # --------------------------------------------------
    # FALLBACK: LOOK INSIDE workflow_state JSON TEXT
    # Handles cases where tracking_key is generic like `node:<id>`
    # --------------------------------------------------
    logger.info(
        "[WAIT_STATE] Trying workflow_state fallback match | rfq_id=%s",
        rfq_id
    )

    state_matches = (
        session.query(WorkflowWaitState)
        .filter(
            WorkflowWaitState.status == "waiting",
            func.lower(cast(WorkflowWaitState.workflow_state, String)).like(f"%{normalized_rfq_key}%"),
        )
        .order_by(WorkflowWaitState.updated_at.desc())
        .all()
    )

    logger.info(
        "[WAIT_STATE] workflow_state fallback results | count=%s",
        len(state_matches)
    )

    for match in state_matches:
        logger.info(
            "[WAIT_STATE STATE MATCH] wait_state_id=%s | workflow_run_id=%s | tracking_key='%s' | tracking_type='%s'",
            match.id,
            match.workflow_run_id,
            match.tracking_key,
            match.tracking_type,
        )

    if len(state_matches) == 1:
        logger.info(
            "[WAIT_STATE] Single workflow_state fallback match selected | wait_state_id=%s",
            state_matches[0].id
        )
        return state_matches[0]

    if state_matches:
        logger.warning(
            "[WAIT_STATE] Multiple workflow_state fallback matches found | rfq_id=%s | count=%s",
            rfq_id,
            len(state_matches),
        )

        rfq_typed_matches = [
            ws for ws in state_matches
            if str(getattr(ws, "tracking_type", "") or "").strip().lower() == "rfq"
        ]

        if rfq_typed_matches:
            selected = rfq_typed_matches[0]
            logger.warning(
                "[WAIT_STATE] Selecting latest RFQ-typed fallback match | wait_state_id=%s | workflow_run_id=%s | tracking_key=%s",
                selected.id,
                selected.workflow_run_id,
                selected.tracking_key,
            )
            return selected

        selected = state_matches[0]
        logger.warning(
            "[WAIT_STATE] Selecting latest fallback match (no RFQ-typed rows) | wait_state_id=%s | workflow_run_id=%s | tracking_key=%s | tracking_type=%s",
            selected.id,
            selected.workflow_run_id,
            selected.tracking_key,
            selected.tracking_type,
        )
        return selected

    logger.warning(
        "[WAIT_STATE] No wait state found | rfq_id=%s",
        rfq_id
    )

    return None

def extract_pincode_from_address(address: str) -> str:
    """
    Extract pincode/postal code from address string.
    Supports:
    - Indian pincodes (6 digits)
    - US ZIP codes (5 digits or 5+4 format)
    - UK postcodes (various formats)
    - Generic 4-6 digit postal codes
    
    Returns: pincode string or None
    """
    if not address or not isinstance(address, str):
        return None
    
    # Remove extra whitespace
    address = address.strip()
    
    # Pattern 1: Indian pincode (6 digits, often at end or standalone)
    # Matches: "560001", "PIN: 560001", "560 001", "560-001"
    indian_pincode = re.search(r'\b(\d{6})\b', address)
    if indian_pincode:
        return indian_pincode.group(1)
    
    # Pattern 2: US ZIP code (5 digits or 5+4 format)
    # Matches: "12345", "12345-6789"
    us_zip = re.search(r'\b(\d{5}(?:-\d{4})?)\b', address)
    if us_zip:
        return us_zip.group(1)
    
    # Pattern 3: UK postcode (various formats like SW1A 1AA, M1 1AA, etc.)
    uk_postcode = re.search(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b', address, re.IGNORECASE)
    if uk_postcode:
        return uk_postcode.group(1).upper()
    
    # Pattern 4: Generic 4-6 digit postal code (fallback)
    generic_pincode = re.search(r'\b(\d{4,6})\b', address)
    if generic_pincode:
        return generic_pincode.group(1)
    
    return None




def get_pincode_details(pincode: str):
    """
    Fetch pincode details using India Post API.
    Works ONLY for Indian pincodes.

    Returns:
        dict with keys: state, district, blocks, post_offices
        OR None if invalid / not found / API error
    """
    if not pincode:
        return None

    pincode = str(pincode).strip()

    # Indian pincode must be exactly 6 digits
    if not pincode.isdigit() or len(pincode) != 6:
        logger.warning("Invalid pincode format: %s", pincode)
        return None

    url = f"https://api.postalpincode.in/pincode/{pincode}"

    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))

    try:
        response = session.get(
            url,
            timeout=5,
            headers={"User-Agent": "RFQ-Service/1.0"}
        )
        response.raise_for_status()

        data = response.json()

        if not data or not isinstance(data, list):
            return None

        result = data[0]

        # API returns Status = "Error" for invalid pincodes
        if result.get("Status") != "Success":
            return None

        post_offices = result.get("PostOffice") or []
        if not post_offices:
            return None

        return {
            "state": post_offices[0].get("State"),
            "district": post_offices[0].get("District"),
            "blocks": list({po.get("Block") for po in post_offices if po.get("Block")}),
            "post_offices": [po.get("Name") for po in post_offices if po.get("Name")]
        }

    except Exception as e:
        logger.exception("Pincode lookup failed for %s", pincode)
        return None


def extract_country_from_address(address: str) -> str:
    """
    Extract country name from address string.
    Looks for common country names at the end of address.
    
    Returns: country string or None
    """
    if not address or not isinstance(address, str):
        return None
    
    # Common country names (case-insensitive)
    countries = [
        "India", "United States", "USA", "US", "United Kingdom", "UK",
        "Canada", "Australia", "Germany", "France", "Italy", "Spain",
        "Netherlands", "Belgium", "Switzerland", "Austria", "Sweden",
        "Norway", "Denmark", "Finland", "Poland", "Portugal", "Greece",
        "Ireland", "New Zealand", "Singapore", "Malaysia", "Thailand",
        "Japan", "China", "South Korea", "Brazil", "Mexico", "Argentina",
        "South Africa", "UAE", "United Arab Emirates", "Saudi Arabia",
        "Qatar", "Kuwait", "Bahrain", "Oman", "Israel", "Turkey", "Russia"
    ]
    
    # Normalize address for matching
    address_lower = address.lower().strip()
    
    # Check for country names (prefer longer matches first)
    countries_sorted = sorted(countries, key=len, reverse=True)
    
    for country in countries_sorted:
        country_lower = country.lower()
        # Check if country appears at the end of address (most common location)
        if address_lower.endswith(country_lower) or \
           address_lower.endswith(country_lower + ".") or \
           address_lower.endswith(country_lower + ","):
            return country
        
        # Also check if country appears as a word boundary (for cases like "Mumbai, India")
        pattern = r'\b' + re.escape(country_lower) + r'\b'
        if re.search(pattern, address_lower):
            # Prefer matches near the end of the address
            match = re.search(pattern, address_lower)
            if match:
                # If match is in last 50 characters, consider it valid
                if match.end() >= len(address_lower) - 50:
                    return country
    
    return None


DEFAULT_LEAD_TIME_DAYS = 10

REQUIRED_MAPPING_FIELDS = [
    "manufacturer_name",
    "manufacturer_product_name"
]

def is_valid_mapping(mapping):
    if not mapping or not isinstance(mapping, list):
        return False

    for m in mapping:
        normalized = {
            key: (m.get(key) or "").strip()
            for key in REQUIRED_MAPPING_FIELDS
        }

        if all(normalized.values()):
            return True

    return False


@rfq_webhook_blueprint.route("/add", methods=["POST"])
def add_rfq():
    session = next(db_session())
    try:
        payload = request.get_json() or {}
        logger.debug("Raw payload received: %s", payload)

        unique_id = generate_rfq_id(session)
        logger.info("Generated new RFQ ID: %s", unique_id)

        due_date = parse_due_date(payload.get("required_delivery_date"))

        customer_address = (
            payload.get("customer_address")
            or payload.get("user_address")
        )

        delivery_address = payload.get("delivery_address")
        if not delivery_address:
            delivery_address = customer_address
            logger.info("No delivery_address provided, using customer_address as fallback")

        delivery_pincode = payload.get("delivery_pincode")
        if not delivery_pincode and delivery_address:
            extracted_pincode = extract_pincode_from_address(delivery_address)
            if extracted_pincode:
                delivery_pincode = extracted_pincode

        delivery_country = payload.get("delivery_country")
        if not delivery_country and delivery_address:
            extracted_country = extract_country_from_address(delivery_address)
            if extracted_country:
                delivery_country = extracted_country

        if not delivery_country and delivery_pincode:
            pincode_details = get_pincode_details(delivery_pincode)
            if pincode_details:
                delivery_country = "India"

        header = RfqHeader(
            sys_rfq_id=unique_id,
            customer_company_name=payload.get("user_company_name"),
            customer_name=payload.get("requested_by"),
            customer_email=payload.get("user_email"),
            customer_address=customer_address,
            delivery_address=delivery_address,
            delivery_pincode=delivery_pincode,
            delivery_country=delivery_country,
            notes=payload.get("notes"),
            rfq_date=datetime.utcnow().date(),
            due_date=due_date.date() if due_date else None
        )

        session.add(header)
        session.flush()

        products = payload.get("products", [])
        logger.debug("Found %d product(s) in payload", len(products))

        if not products:
            raise Exception("No products provided for RFQ")

        valid_items_added = 0

        for idx, p in enumerate(products, start=1):
            lead_time_days = safe_int(p.get("lead_time_days"))
            mapping = p.get("mapping_json")

            # 🔒 NEW STRICT VALIDATION
            if not is_valid_mapping(mapping):
                logger.warning(
                    "Skipping product %d: Required mapping fields missing | description=%s",
                    idx,
                    p.get("product_description")
                )
                continue

            item = RfqLineItems(
                sys_rfq_id=unique_id,
                customer_part_number=p.get("customer_part_number"),
                product_description=p.get("product_description"),
                quantity=safe_int(p.get("quantity")) or 0,
                uom=p.get("uom"),
                lead_time_days=(
                    lead_time_days if lead_time_days is not None else DEFAULT_LEAD_TIME_DAYS
                ),
                remarks=p.get("remarks"),
                mapping_json=mapping
            )

            session.add(item)
            valid_items_added += 1

        # 🚫 Prevent empty RFQ creation
        if valid_items_added == 0:
            session.rollback()
            logger.error("RFQ aborted: No valid mapped products found")
            return jsonify({
                "status": False,
                "error": "No valid mapped products found. RFQ not created."
            }), 400

        session.commit()
        logger.info(
            "RFQ committed | valid_products: %d / total_products: %d",
            valid_items_added,
            len(products)
        )

        rfq_line_ids = [
            item.rfq_line_id
            for item in session.query(RfqLineItems.rfq_line_id)
                .filter_by(sys_rfq_id=unique_id)
                .all()
        ]

        return jsonify({
            "status": True,
            "message": "RFQ created successfully",
            "sys_rfq_id": unique_id,
            "rfq_line_ids": rfq_line_ids
        }), 201

    except Exception as e:
        session.rollback()
        logger.error(
            "Failed to create RFQ | sys_rfq_id: %s | Error: %s",
            unique_id if 'unique_id' in locals() else 'N/A',
            str(e),
            exc_info=True
        )
        return jsonify({"status": False, "error": str(e)}), 500

    finally:
        session.close()

@rfq_webhook_blueprint.route("/update", methods=["POST"])
def update_rfq():
    session = next(db_session())
    try:
        payload = request.get_json() or {}
        sys_rfq_id = payload.get("rfq_no")

        if not sys_rfq_id:
            return jsonify({"status": False, "message": "Missing rfq_no"}), 400

        rfq = session.query(RfqHeader).filter_by(sys_rfq_id=sys_rfq_id).first()

        if not rfq:
            return jsonify({"status": False, "message": "RFQ not found"}), 404

        editable_fields = [
            "customer_company_name", "customer_name", "customer_email",
            "notes", "currency", "delivery_address", "due_date","delivery_pincode","delivery_country","customer_address"
        ]

        for field in editable_fields:
            if field in payload:
                setattr(rfq, field, payload[field])

        rfq.updated_at = datetime.utcnow()
        session.commit()

        return jsonify({"status": True, "message": "RFQ updated successfully", "sys_rfq_id": sys_rfq_id})

    except Exception as e:
        session.rollback()
        return jsonify({"status": False, "error": str(e)}), 500
    finally:
        session.close()

@rfq_webhook_blueprint.route("/<string:sys_rfq_id>", methods=["GET"])
def get_rfq(sys_rfq_id):
    session = next(db_session())
    try:
        rfq = session.query(RfqHeader).filter_by(sys_rfq_id=sys_rfq_id).first()

        if not rfq:
            return jsonify({"status": False, "message": "RFQ not found"}), 404

        header_data = {col.name: getattr(rfq, col.name) for col in rfq.__table__.columns}

        line_items = [
            {col.name: getattr(item, col.name) for col in item.__table__.columns}
            for item in rfq.line_items
        ]

        return jsonify({
            "status": True,
            "rfq_header": header_data,
            "line_items": line_items
        })

    except Exception as e:
        return jsonify({"status": False, "error": str(e)}), 500
    finally:
        session.close()


@rfq_webhook_blueprint.route("/fetch", methods=["POST"])
def fetch_rfq():
    session = next(db_session())
    try:
        data = request.get_json()
        sys_rfq_id = data.get("rfq_no")

        rfq = session.query(RfqHeader).filter_by(sys_rfq_id=sys_rfq_id).first()
        if not rfq:
            return jsonify({"status": False, "message": "RFQ not found"}), 404

        return jsonify({
            "status": True,
            "message": "RFQ data fetched successfully",

            "rfq_header": {
                col.name: getattr(rfq, col.name)
                for col in rfq.__table__.columns
                if col.name not in {"created_at", "updated_at", "deleted_flag"}
            },

            "line_items": [
                {
                    col.name: getattr(item, col.name)
                    for col in item.__table__.columns
                    if col.name not in {"created_at", "updated_at", "deleted_flag"}
                }
                for item in rfq.line_items
            ]
        })

    except Exception as e:
        return jsonify({"status": False, "error": str(e)}), 500
    finally:
        session.close()



@rfq_webhook_blueprint.route("/fetch-all-summary", methods=["POST"])
def fetch_all_rfqs_summary():
    session = next(db_session())
    try:
        data = request.get_json(silent=True) or {}

        # -----------------------------
        # Pagination params
        # -----------------------------
        page = max(int(data.get("page", 1)), 1)
        page_size = max(int(data.get("page_size", 10)), 1)
        offset = (page - 1) * page_size

        include_deleted = data.get("include_deleted", False)

        # -----------------------------
        # Base RFQ query
        # -----------------------------
        rfq_query = session.query(RfqHeader)

        if not include_deleted:
            rfq_query = rfq_query.filter(RfqHeader.deleted_flag == False)

        total_records = rfq_query.count()

        rfqs = (
            rfq_query
            .order_by(RfqHeader.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        # -----------------------------
        # Aggregate quotations (new + legacy flows)
        # -----------------------------
        logger.info("RFQs on page: %s", [r.sys_rfq_id for r in rfqs])

        stats_map = {}
        for rfq in rfqs:
            rfq_key_norm = (rfq.sys_rfq_id or "").strip().lower()

            # New flow counts
            new_sent = (
                session.query(func.count(SupplierQuotation.supplier_quotation_id))
                .filter(
                    or_(
                        func.lower(func.trim(SupplierQuotation.sys_rfq_id)) == rfq_key_norm,
                        func.lower(func.trim(SupplierQuotation.customer_rfq_number)) == rfq_key_norm,
                    )
                )
                .scalar()
            ) or 0

            new_received = (
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

            # Legacy flow counts
            legacy_sent = (
                session.query(func.count(SupplierQuotations.id))
                .filter(func.lower(func.trim(SupplierQuotations.rfq_no)) == rfq_key_norm)
                .scalar()
            ) or 0

            legacy_received = (
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

            # Prefer new flow values when present
            if new_sent > 0:
                stats_map[rfq.sys_rfq_id] = {"sent": int(new_sent), "received": int(new_received)}
            elif legacy_sent > 0:
                stats_map[rfq.sys_rfq_id] = {"sent": int(legacy_sent), "received": int(legacy_received)}
            else:
                stats_map[rfq.sys_rfq_id] = {"sent": 0, "received": 0}

        # -----------------------------
        # Build response
        # -----------------------------
        rfq_list = []
        for rfq in rfqs:
            stats = stats_map.get(rfq.sys_rfq_id, {"sent": 0, "received": 0})
            sent_count = int(stats["sent"] or 0)
            received_count = int(stats["received"] or 0)
            quotation_percentage = int((received_count / sent_count) * 100) if sent_count > 0 else 0

            rfq_list.append({
                # ---- RFQ HEADER ----
                "sys_rfq_id": rfq.sys_rfq_id,
                "customer_rfq_number": rfq.customer_rfq_number,
                "customer_company_name": rfq.customer_company_name,
                "customer_name": rfq.customer_name,
                "customer_email": rfq.customer_email,
                "rfq_date": rfq.rfq_date.isoformat() if rfq.rfq_date else None,
                "due_date": rfq.due_date.isoformat() if rfq.due_date else None,
                "currency": rfq.currency,
                "delivery_country": rfq.delivery_country,
                "notes": rfq.notes,
                "created_at": rfq.created_at.isoformat(),
                "updated_at": rfq.updated_at.isoformat(),

                # ---- SUMMARY ----
                "total_quotations_sent": sent_count,
                "total_quotations_received": received_count,
                # Compatibility aliases for different frontend builds
                "quotation_sent_count": sent_count,
                "quotation_received_count": received_count,
                "total_quotations": sent_count,
                "received_quotations": received_count,
                "quotation_display_count": f"{received_count}/{sent_count}",
                "quotation_progress_percentage": quotation_percentage
            })

        # -----------------------------
        # Pagination metadata
        # -----------------------------
        total_pages = (total_records + page_size - 1) // page_size

        return jsonify({
            "status": True,
            "message": "RFQ summary list fetched successfully",
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_records": total_records,
                "total_pages": total_pages
            },
            "rfqs": rfq_list
        })

    except Exception as e:
        return jsonify({
            "status": False,
            "error": str(e)
        }), 500

    finally:
        session.close()
        
        


# -------------- Finalize RFQ Routes ---------------




FUZZY_MATCH_THRESHOLD = 90


def resolve_supplier_quotation_id(session, rfq_id, supplier_name):
    """
    Resolve supplier_quotation_id using fuzzy matching on supplier_name.
    Accepts match only if confidence >= 90%.
    """

    # 1️⃣ Fetch all supplier quotations for the RFQ
    rows = session.execute(
        text("""
            SELECT supplier_quotation_id, supplier_name
            FROM supplier_quotations_new
            WHERE sys_rfq_id = :rfq_id
        """),
        {"rfq_id": rfq_id}
    ).fetchall()

    if not rows:
        raise ValueError(
            f"No supplier quotations found for RFQ {rfq_id}"
        )

    # 2️⃣ Build lookup map
    supplier_name_map = {
        row[1]: row[0] for row in rows
    }

    # 3️⃣ Perform fuzzy matching
    match_name, score, _ = process.extractOne(
        supplier_name,
        supplier_name_map.keys(),
        scorer=fuzz.token_sort_ratio
    )

    # 4️⃣ Permissive behavior: accept best fuzzy match even at low confidence
    if score < FUZZY_MATCH_THRESHOLD:
        logger.warning(
            "[FINALIZE BUILD] Low confidence supplier match accepted | rfq_id=%s input=%s best_match=%s score=%s threshold=%s",
            rfq_id,
            supplier_name,
            match_name,
            score,
            FUZZY_MATCH_THRESHOLD,
        )

    # 5️⃣ Return matched supplier_quotation_id
    return supplier_name_map[match_name]
def build_finalize_payload_from_processed(processed_payload, session):
    """
    Maps processed RFQ JSON into finalize payload
    WITHOUT changing finalize core logic.
    """

    data = processed_payload.get("data", {})

    rfq_id = data.get("rfq_no")
    processed_json = data.get("processed_json")

    if not rfq_id or not processed_json:
        raise ValueError("Invalid processed RFQ payload")

    finalized_suppliers = []

    quotation_combination = processed_json.get("quotation_combination", {})

    if not quotation_combination:
        raise ValueError("No quotation_combination found in processed JSON")

    for quotation_key, quotation_data in quotation_combination.items():
        if not isinstance(quotation_data, dict):
            logger.info(
                "[FINALIZE BUILD] Skipping non-dict quotation entry | rfq_id=%s quotation_key=%s type=%s",
                rfq_id,
                quotation_key,
                type(quotation_data).__name__,
            )
            continue

        for key, supplier_block in quotation_data.items():

            if key in {
                "rank", "total_price", "lead_time", "total_weight",
                "bank_charges", "clearance_charges", "freight_charges",
                "freight_delivery_partner", "oversize_charge",
                "Surge_Fee", "local_charges", "local_delivery_partner",
                "total_landed_cost", "total_dimention",
                "partial_fulfillment", "evaluation_parameters","shipment_type"
            }:
                continue

            # Only supplier blocks should be finalized.
            # Sometimes quotation payloads can include metadata-like keys
            # (e.g. supplier_country) at the same level.
            if not isinstance(supplier_block, dict):
                logger.info(
                    "[FINALIZE BUILD] Skipping non-dict quotation key | rfq_id=%s quotation_key=%s key=%s type=%s",
                    rfq_id,
                    quotation_key,
                    key,
                    type(supplier_block).__name__,
                )
                continue

            supplier_name = key

            supplier_quotation_id = resolve_supplier_quotation_id(
                session, rfq_id, supplier_name
            )

            items = []
            for material_no, material_data in supplier_block.items():
                if material_no == "supplier_country":
                    continue

                items.append({
                    "rfq_line_id": material_no,
                    "finalized_quantity": material_data.get("allocated_qty")
                })

            finalized_suppliers.append({
                "supplier_quotation_id": supplier_quotation_id,
                "finalized_json": quotation_data,
                "items": items
            })

    # ✅ THIS RETURN WAS MISSING (CRITICAL)
    return {
        "sys_rfq_id": rfq_id,
        "finalized_suppliers": finalized_suppliers,
        "finalized_quotation_json": processed_json
    }

import threading
from datetime import datetime
import json
from flask import request
from sqlalchemy import text


def resume_wait_node_for_rfq(session, rfq_id: str, event_payload: dict | None = None):
    """
    Trigger workflow resume for RFQ wait node.
    CORE LOGIC UNCHANGED — ONLY SAFETY + LOGS ADDED
    """

    logger.info(
        "[RESUME] RFQ resume requested | rfq_id=%s payload_keys=%s",
        rfq_id,
        list((event_payload or {}).keys()),
    )

    wait_state = _find_wait_state_by_rfq(session, rfq_id)

    if not wait_state:
        logger.info(
            "[RESUME] No waiting state found | rfq_id=%s",
            rfq_id,
        )
        return None

    wait_state_id = wait_state.id

    logger.info(
        "[RESUME] Wait state found | wait_id=%s run_id=%s node_id=%s diagram_id=%s",
        wait_state.id,
        wait_state.workflow_run_id,
        wait_state.node_id,
        wait_state.diagram_id,
    )

    workflow_row = (
        session.query(BotDiagram)
        .filter(BotDiagram.diagram_id == int(wait_state.diagram_id))
        .filter(BotDiagram.del_flg == False)
        .filter(func.lower(func.coalesce(BotDiagram.status, "")) != "deleted")
        .first()
    )

    if not workflow_row:
        raise Exception("Workflow diagram not found")

    workflow_json = json.loads(workflow_row.diagram_json)
    workflow_json.update(
        {
            "bot_id": int(wait_state.bot_id),
            "tenant_id": int(wait_state.tenant_id),
            "diagram_id": int(wait_state.diagram_id),
        }
    )

    logger.info(
        "[RESUME] Workflow loaded | bot_id=%s diagram_id=%s",
        wait_state.bot_id,
        wait_state.diagram_id,
    )

    # 🔒 Close caller session BEFORE executor starts
    session.close()

    executor = WorkflowExecutor(workflow_json)

    logger.info(
        "[RESUME] Invoking executor.resume_from_wait_state | wait_state_id=%s",
        wait_state_id,
    )

    executor.resume_from_wait_state(
        wait_state_id=wait_state_id,
        event_payload=event_payload or {},
    )

    logger.info(
        "[RESUME] Resume invocation finished | wait_state_id=%s",
        wait_state_id,
    )

    return True


def _async_workflow_resume(rfq_id: str):
    """
    Background task to resume workflow after RFQ finalization.
    Runs in a separate thread with its own DB session.
    """
    try:
        logger.info("[ASYNC-RESUME] Starting background workflow resume for RFQ=%s", rfq_id)
        
        # Create fresh session for background thread
        session = next(db_session())
        
        try:
            wait_state = resume_wait_node_for_rfq(
                session=session,
                rfq_id=rfq_id,
                event_payload={
                    "event": "rfq_finalized",
                    "rfq_id": rfq_id
                }
            )
            
            session.commit()
            
            logger.info(
                "[ASYNC-RESUME] Completed RFQ=%s workflow_resumed=%s",
                rfq_id,
                bool(wait_state)
            )
            
        except Exception as e:
            session.rollback()
            logger.exception("[ASYNC-RESUME ERROR] RFQ=%s", rfq_id)
            
        finally:
            session.close()
            
    except Exception as e:
        logger.exception("[ASYNC-RESUME FATAL ERROR] RFQ=%s", rfq_id)


@rfq_webhook_blueprint.route("/finalize", methods=["POST"])
def finalize_rfq():
    session = next(db_session())
    try:
        logger.info("========== [FINALIZE START] ==========")

        # -------------------------------
        # 1️⃣ INPUT VALIDATION
        # -------------------------------
        incoming_payload = request.get_json()

        logger.info("[INPUT] Raw Payload: %s", incoming_payload)

        if not incoming_payload:
            logger.warning("[FINALIZE] Empty payload received")
            return {"status": "error", "message": "Invalid payload"}, 400

        # -------------------------------
        # 2️⃣ BUILD DATA
        # -------------------------------
        data = build_finalize_payload_from_processed(incoming_payload, session)

        logger.info("[BUILD] Finalized Data: %s", data)

        rfq_id = data["sys_rfq_id"]
        suppliers = data["finalized_suppliers"]
        rfq_json = data["finalized_quotation_json"]

        logger.info("[DATA] RFQ ID: %s", rfq_id)
        logger.info("[DATA] Suppliers Count: %d", len(suppliers))

        # -------------------------------
        # 3️⃣ RESET OLD DATA
        # -------------------------------
        logger.info("[DB] Resetting old supplier data for RFQ=%s", rfq_id)

        session.execute(text("""
            UPDATE supplier_quotations_new
            SET is_finalized = FALSE,
                finalized_at = NULL,
                finalized_json = NULL
            WHERE sys_rfq_id = :rfq_id
        """), {"rfq_id": rfq_id})

        # -------------------------------
        # 4️⃣ PROCESS SUPPLIERS
        # -------------------------------
        for s in suppliers:
            logger.info("[SUPPLIER] Processing: %s", s)

            supplier_id = s["supplier_quotation_id"]

            # Update supplier
            logger.info("[DB] Updating supplier_id=%s", supplier_id)
            session.execute(text("""
                UPDATE supplier_quotations_new
                SET is_finalized = TRUE,
                    finalized_at = NOW(),
                    finalized_json = :finalized_json
                WHERE supplier_quotation_id = :supplier_id
                  AND sys_rfq_id = :rfq_id
            """), {
                "supplier_id": supplier_id,
                "rfq_id": rfq_id,
                "finalized_json": json.dumps(s.get("finalized_json", {}))
            })

            result = session.execute(text("""
                SELECT sys_rfq_id, status, finalized_at
                FROM rfq_header
                WHERE sys_rfq_id = :rfq_id
            """), {"rfq_id": rfq_id}).fetchone()

            if result:
                logger.info("[VERIFY] RFQ HEADER: %s", dict(result._mapping))
            else:
                logger.warning("[VERIFY] RFQ HEADER NOT FOUND")

            # Reset line items
            logger.info("[DB] Resetting line items for supplier_id=%s", supplier_id)

            session.execute(text("""
                UPDATE supplier_quotation_line_items
                SET is_selected = FALSE,
                    finalized_quantity = NULL
                WHERE supplier_quotation_id = :supplier_id
            """), {"supplier_id": supplier_id})

            # Update selected items
            for item in s["items"]:
                logger.info(
                    "[ITEM] supplier_id=%s material_no=%s qty=%s",
                    supplier_id,
                    item["rfq_line_id"],
                    item["finalized_quantity"]
                )

                session.execute(text("""
                    UPDATE supplier_quotation_line_items
                    SET is_selected = TRUE,
                        finalized_quantity = :qty
                    WHERE supplier_quotation_id = :supplier_id
                      AND material_no = :material_no
                """), {
                    "supplier_id": supplier_id,
                    "material_no": item["rfq_line_id"],
                    "qty": item["finalized_quantity"]
                })

        # -------------------------------
        # 5️⃣ UPDATE RFQ HEADER
        # -------------------------------
        logger.info("[DB] Updating RFQ header for RFQ=%s", rfq_id)

        session.execute(text("""
            UPDATE rfq_header
            SET status = 'Completed',
                finalized_at = NOW(),
                finalized_quotation_json = :json
            WHERE sys_rfq_id = :rfq_id
        """), {
            "rfq_id": rfq_id,
            "json": json.dumps(rfq_json)
        })

        # -------------------------------
        # 6️⃣ COMMIT
        # -------------------------------
        logger.info("[DB] Committing transaction...")
        session.commit()
        logger.info("[DB] Commit successful")

        # -------------------------------
        # 7️⃣ VERIFY DB WRITE (IMPORTANT)
        # -------------------------------
        logger.info("[VERIFY] Checking DB values after commit")

        result = session.execute(text("""
            SELECT sys_rfq_id, status, finalized_at
            FROM rfq_header
            WHERE sys_rfq_id = :rfq_id
        """), {"rfq_id": rfq_id}).fetchone()

        logger.info("[VERIFY] RFQ HEADER: %s",dict(result._mapping) if result else "NOT FOUND")

        supplier_check = session.execute(text("""
            SELECT supplier_quotation_id, is_finalized
            FROM supplier_quotations_new
            WHERE sys_rfq_id = :rfq_id
        """), {"rfq_id": rfq_id}).fetchall()

        logger.info("[VERIFY] SUPPLIERS: %s", [dict(row._mapping) for row in supplier_check])

        # -------------------------------
        # 8️⃣ ASYNC WORKFLOW
        # -------------------------------
        logger.info("[ASYNC] Starting workflow thread for RFQ=%s", rfq_id)

        resume_thread = threading.Thread(
            target=_async_workflow_resume,
            args=(rfq_id,),
            daemon=True
        )
        resume_thread.start()

        # -------------------------------
        # 9️⃣ RESPONSE
        # -------------------------------
        logger.info("========== [FINALIZE SUCCESS] ==========")

        return {
            "status": "success",
            "rfq_id": rfq_id,
            "message": "RFQ finalized successfully. Workflow running in background."
        }, 200

    except Exception as e:
        session.rollback()
        logger.exception("[FINALIZE ERROR]")
        return {"status": "error", "message": str(e)}, 500

    finally:
        session.close()
        logger.info("========== [FINALIZE END] ==========")

@rfq_webhook_blueprint.route("/<rfq_id>/finalization-status", methods=["GET"])
def rfq_finalization_status(rfq_id):
    session = next(db_session())
    try:
        logger.info("========== [FINALIZATION-STATUS START] ==========")
        logger.info("[STATUS] Request received | rfq_id=%s", rfq_id)

        row = session.execute(
            text("""
                SELECT
                    status,
                    finalized_quotation_json,
                    customer_company_name,
                    customer_name,
                    customer_email,
                    customer_address,
                    delivery_address,
                    currency
                FROM rfq_header
                WHERE sys_rfq_id = :rfq_id
            """),
            {"rfq_id": rfq_id}
        ).fetchone()
        logger.info("[STATUS] Header query executed | rfq_id=%s found=%s", rfq_id, bool(row))

        # 1️⃣ RFQ not found
        if not row:
            logger.warning("[STATUS] Invalid RFQ ID | rfq_id=%s", rfq_id)
            return {
                "finalized": False,
                "error": "INVALID_RFQ_ID",
                "message": f"RFQ {rfq_id} does not exist"
            }, 404

        (
            status,
            finalized_json,
            customer_company_name,
            customer_name,
            customer_email,
            customer_address,
            delivery_address,
            currency
        ) = row
        logger.info(
            "[STATUS] Header values | rfq_id=%s status=%s has_finalized_json=%s",
            rfq_id,
            status,
            bool(finalized_json),
        )

        # 2️⃣ RFQ not finalized
        if status != "Completed":
            logger.info(
                "[STATUS] RFQ not finalized yet | rfq_id=%s current_status=%s",
                rfq_id,
                status,
            )
            return {
                "finalized": False,
                "rfq_id": rfq_id,
                "status": status
            }, 200

        # -------------------------------
        # 🔹 RESPONSE SHAPING STARTS HERE
        # -------------------------------
        if not isinstance(finalized_json, dict):
            logger.warning(
                "[STATUS] finalized_quotation_json invalid type | rfq_id=%s type=%s",
                rfq_id,
                type(finalized_json).__name__,
            )
            finalized_json = {}

        normalized_rfq_key = _normalize_tracking_key(rfq_id)
        wait_state_rows = (
            session.query(
                WorkflowWaitState.id,
                WorkflowWaitState.workflow_run_id,
                WorkflowWaitState.node_id,
                WorkflowWaitState.diagram_id,
                WorkflowWaitState.tracking_key,
                WorkflowWaitState.tracking_type,
                WorkflowWaitState.status,
                WorkflowWaitState.updated_at,
            )
            .filter(WorkflowWaitState.status == "waiting")
            .filter(
                or_(
                    func.lower(func.trim(WorkflowWaitState.tracking_key)) == normalized_rfq_key,
                    func.lower(cast(WorkflowWaitState.workflow_state, String)).like(f"%{normalized_rfq_key}%"),
                )
            )
            .order_by(WorkflowWaitState.updated_at.desc())
            .all()
        )
        logger.info(
            "[STATUS] Matching wait-state diagnostics | rfq_id=%s normalized_key=%s matches=%s",
            rfq_id,
            normalized_rfq_key,
            len(wait_state_rows),
        )
        for ws in wait_state_rows:
            logger.info(
                "[STATUS WAIT_STATE] id=%s run_id=%s node_id=%s diagram_id=%s tracking_key=%s tracking_type=%s status=%s updated_at=%s",
                ws.id,
                ws.workflow_run_id,
                ws.node_id,
                ws.diagram_id,
                ws.tracking_key,
                ws.tracking_type,
                ws.status,
                ws.updated_at,
            )

        quotation_combination = finalized_json.get("quotation_combination", {})
        logger.info(
            "[STATUS] quotation_combination parsed | rfq_id=%s combinations=%s",
            rfq_id,
            len(quotation_combination) if isinstance(quotation_combination, dict) else 0,
        )

        if not isinstance(quotation_combination, dict):
            logger.warning(
                "[STATUS] quotation_combination invalid type | rfq_id=%s type=%s",
                rfq_id,
                type(quotation_combination).__name__,
            )
            quotation_combination = {}

        suppliers = []
        finalized_summary = {}
        summary_keys = {
            "rank", "total_price", "lead_time", "total_weight",
            "bank_charges", "clearance_charges", "freight_charges",
            "freight_delivery_partner", "oversize_charge",
            "Surge_Fee", "local_charges", "local_delivery_partner",
            "total_landed_cost", "total_dimention",
            "partial_fulfillment", "evaluation_parameters", "shipment_type"
        }

        for quotation_key, quotation_data in (
            quotation_combination.items() if isinstance(quotation_combination, dict) else []
        ):
            if not isinstance(quotation_data, dict):
                logger.debug(
                    "[STATUS] Quotation entry skipped (non-dict) | rfq_id=%s quotation_key=%s value_type=%s",
                    rfq_id,
                    quotation_key,
                    type(quotation_data).__name__,
                )
                continue

            logger.info(
                "[STATUS] quotation entry extracted | rfq_id=%s quotation_key=%s keys=%s",
                rfq_id,
                quotation_key,
                list(quotation_data.keys()),
            )

            quotation_level_supplier_country = quotation_data.get("supplier_country")

            for key, value in quotation_data.items():
                if key in summary_keys:
                    if key not in finalized_summary:
                        finalized_summary[key] = value
                    logger.debug(
                        "[STATUS] Summary field captured | rfq_id=%s quotation_key=%s field=%s",
                        rfq_id,
                        quotation_key,
                        key,
                    )
                    continue

                if not isinstance(value, dict):
                    logger.debug(
                        "[STATUS] Unclassified quotation key skipped | rfq_id=%s quotation_key=%s key=%s value_type=%s",
                        rfq_id,
                        quotation_key,
                        key,
                        type(value).__name__,
                    )
                    continue

                supplier_items = []
                for item_key, item_val in value.items():
                    if item_key == "supplier_country":
                        continue
                    if isinstance(item_val, dict):
                        supplier_items.append(item_val)

                supplier_country = (
                    value.get("supplier_country")
                    if isinstance(value.get("supplier_country"), str)
                    else quotation_level_supplier_country
                )

                suppliers.append({
                    "supplier_name": key,
                    "supplier_country": supplier_country,
                    "items": supplier_items,
                })
                logger.info(
                    "[STATUS] Supplier parsed | rfq_id=%s quotation_key=%s supplier=%s country=%s items=%s",
                    rfq_id,
                    quotation_key,
                    key,
                    supplier_country,
                    len(supplier_items),
                )

        logger.info(
            "[STATUS] Response ready | rfq_id=%s suppliers=%s summary_fields=%s",
            rfq_id,
            len(suppliers),
            len(finalized_summary),
        )

        return {
            "finalized": True,
            "rfq_id": rfq_id,

            "customer": {
                "company_name": customer_company_name,
                "contact_name": customer_name,
                "email": customer_email,
                "address": customer_address,
                "delivery_address": delivery_address,
                "currency": currency
            },

            "suppliers": suppliers,

            "finalized_summary": finalized_summary
        }, 200

    except Exception as e:
        logger.error(f"[STATUS ERROR] {e}", exc_info=True)
        return {
            "status": "error",
            "message": "Internal server error"
        }, 500

    finally:
        session.close()
        logger.info("[STATUS] DB session closed | rfq_id=%s", rfq_id)
        logger.info("========== [FINALIZATION-STATUS END] ==========")

from app.models import WorkflowWaitState,BotDiagram
from engine.workflow_executor import WorkflowExecutor


@rfq_webhook_blueprint.route("/trigger-resume/<rfq_id>", methods=["POST"])
def manual_trigger_resume(rfq_id):
    """
    Resume workflow execution from WaitNode using RFQ ID.
    This is event-driven resume (NO polling, NO re-execute).
    """

    session = next(db_session())

    try:
        # --------------------------------------------------
        # 1️⃣ Fetch waiting state (lock row to avoid double resume)
        # --------------------------------------------------
        wait_state = _find_wait_state_by_rfq(session, rfq_id)

        if not wait_state:
            return jsonify({
                "error": f"No waiting workflow found for RFQ {rfq_id}"
            }), 404

        logger.info(
            f"[MANUAL_RESUME] Resuming workflow_run_id={wait_state.workflow_run_id} "
            f"node_id={wait_state.node_id}"
        )

        # --------------------------------------------------
        # 2️⃣ Load workflow definition
        # --------------------------------------------------
        workflow_json = (
            session.query(BotDiagram)
            .filter(BotDiagram.diagram_id == int(wait_state.diagram_id))
            .filter(BotDiagram.del_flg == False)
            .filter(func.lower(func.coalesce(BotDiagram.status, "")) != "deleted")
            .first()
        )

        if not workflow_json:
            return jsonify({
                "error": "Workflow diagram not found"
            }), 404

        import json
        workflow_json = json.loads(workflow_json.diagram_json)

        workflow_json.update({
            "bot_id": int(wait_state.bot_id),
            "tenant_id": int(wait_state.tenant_id),
            "diagram_id": int(wait_state.diagram_id),
        })

        # --------------------------------------------------
        # 3️⃣ Mark wait state as completed BEFORE resume
        # --------------------------------------------------
        wait_state.status = "completed"
        wait_state.completed_at = datetime.utcnow()
        session.flush()  # DO NOT commit yet

        # --------------------------------------------------
        # 4️⃣ Resume workflow from WaitNode
        # --------------------------------------------------
        executor = WorkflowExecutor(workflow_json)
        executor.session_ref = session

        executor.resume_from_wait_state(
            wait_state=wait_state,
            event_payload=request.get_json(silent=True) or {}
        )

        # --------------------------------------------------
        # 5️⃣ Commit transaction
        # --------------------------------------------------
        session.commit()

        return jsonify({
            "status": "resumed",
            "rfq_id": rfq_id,
            "workflow_run_id": wait_state.workflow_run_id,
            "wait_state_id": wait_state.id
        }), 200

    except Exception as e:
        session.rollback()
        logger.exception("[MANUAL_RESUME] Resume failed")
        return jsonify({"error": str(e)}), 500

    finally:
        session.close()
