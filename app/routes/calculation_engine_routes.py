from flask import Blueprint, jsonify, request
from logging_config import setup_logging
from app.database.DatabaseOperationPostgreSQL import db_session
from app.satya_charges_utils.rfq_service import get_rfq, get_rfq_items
from app.satya_charges_utils.supplier_service import (
    get_suppliers,
    get_supplier_items,
)
from sqlalchemy import func
from rapidfuzz import process, fuzz
import re
from app.models.charges_models import FedexOriginZoneConfig,FedexFreightCharge,UPSOriginZoneConfig,UPSFreightCharge
from app.satya_charges_utils.charge_service import (
    get_zone,
    calculate_fedex_freight_charge,
)
from app.satya_charges_utils.derive_service import (
    derive_total_shipment_weight,
    derive_delivery_category,
)
# UPDATED: Import static charges instead of DB queries
from app.routes.static_charges import (
    get_charges,
    override_charges,
    clear_overrides,
)
from app.routes.satya_charges_utils.static_charges_adapter import (
    build_bank_charges_from_static,
    build_clearance_charges_from_static,
    build_local_freight_charges_from_static,
    build_other_charges_from_static,
    calculate_bank_charges_amount,
    calculate_clearance_charges_amount,
    calculate_local_freight_amount,
)
import json
import uuid

logger = setup_logging(
    name="calculation_engine-json-builder",
    level="INFO",
    group="charges"
)

calculation_engine_routes = Blueprint(
    "calculation_engine_routes",
    __name__,
    url_prefix="/calculation_engine"
)

# --------------------------------------------------
# CONSTANTS
# --------------------------------------------------

LOCAL_ROUTE_TYPE_MAP = {
    "within_city": "Within City",
    "within_metro": "Metros",
    "within_state": "Within State",
    "within_zone": "Within Zone",
    "special_destination": "Special destination",
    "rest_of_india": "Rest of india",
}

SHIPMENT_MAP = {
    "cargo_gt_1_lakh": "GTL",
    "courier_lt_1_lakh": "LTL",
    "freight_forwarder": "FF"
}

# --------------------------------------------------
# Charge mapping rules
# --------------------------------------------------
CHARGE_RULES = [
    {
        "match": ["advancement"],
        "field": "advancement_charge",
        "use_min": True,
    },
    {
        "match": ["clearance charges"],   
        "field": "clearance_charge",
        "use_min": True,
    },
    {
        "match": ["formal boe", "formal_boe"],
        "field": "formal_boe_charge",
        "use_min": True,
    },
    {
        "match": ["documentation"],
        "field": "documentation_charge_per_AWB",
        "use_min": True,
    },
    {
        "match": ["courier handling"],
        "field": "courier_handling_charges",
        "use_min": True,
        "per_kg_field": "courier_handling_charges_per_kg",
    },
    {
        "match": ["tsp charges - general", "tsp_general", "tsp general"],
        "field": "TSP_general_charge",
        "use_min": True,
        "per_kg_field": "TSP_general_charge_prise_per_kg",
    },
    {
        "match": ["tsp charges - special", "tsp_special", "tsp special"],
        "field": "TSP_special_cargo_charge",
        "use_min": True,
        "per_kg_field": "TSP_special_cargo_charge_prise_per_kg",
    },
    {
        "match": ["demurrage charges - general", "demurrage_general", "demurrage general"],
        "field": "demurrage_charges_General",
        "use_min": True,
        "per_kg_field": "demurrage_charges_General_prise_per_kg",
    },
    {
        "match": ["demurrage charges - special", "demurrage_special", "demurrage special"],
        "field": "demurrage_special_cargo_charges",
        "use_min": True,
        "per_kg_field": "demurrage_special_cargo_charges_prise_per_kg",
    },
    {
        "match": ["transportation"],
        "field": "transportation_charges",
        "use_min": True,
    },
    {
        "match": ["do fee"],
        "field": "DO_fee",
        "use_min": True,
    },
]


DEFAULT_FREIGHT_PARTNERS = {"FEDEX"}
ALL_FREIGHT_PARTNERS = {"FEDEX", "UPS"}
COMMON_CARRIER = "COMMON"


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def fmt(val):
    """Format value to 2 decimal places or return None"""
    return f"{float(val):.2f}" if val is not None else None


# ----------------- Devlivery type / parnter utils -----------------
def derive_delivery_type(suppliers):
    """
    TEMP: Derive delivery type using primary supplier (suppliers[0]).

    Returns:
        "global" | "local"
    """

    if not suppliers:
        return None

    primary = suppliers[0]

    # TEMP rule:
    # If freight delivery partner exists → global
    if primary.freight_delivery_partner:
        return "global"

    return "local"

# NOTE: derive_delivery_partner is intentionally unused for now.
# Will be used when delivery partner becomes supplier-specific.
def derive_delivery_partner(suppliers, delivery_type):
    """
    TEMP: Derive delivery partner details using primary supplier (suppliers[0]).

    Args:
        suppliers: list of SupplierQuotation
        delivery_type: "local" | "global"

    Returns:
        dict | None
        {
            "partner": str,
            "type": str
        }
    """

    if not suppliers:
        return None

    primary = suppliers[0]

    if delivery_type == "global":
        if not primary.freight_delivery_partner:
            return None

        return {
            "partner": primary.freight_delivery_partner.lower(),
            "type": primary.freight_delivery_partner_type
        }

    if delivery_type == "local":
        if not primary.local_delivery_partner:
            return None

        return {
            "partner": primary.local_delivery_partner.lower(),
            "type": primary.local_delivery_partner_type
        }

    return None

def derive_clearance_shipment_type(suppliers, delivery_type):
    """
    Derive clearance shipment type as delivery partner.
    """

    if not suppliers or delivery_type != "global":
        return None

    primary = suppliers[0]

    if not primary.freight_delivery_partner:
        return None

    partner = primary.freight_delivery_partner.lower()

    if partner in ("fedex", "ups"):
        return partner

    return "freight_forwarder"


# ----------------------------------------------------------



def build_suppliers_json(suppliers, supplier_items_map):
    result = []

    for supplier in suppliers:
        s_json = {
            "supplier_name": supplier.supplier_name,
            "supplier_country": supplier.supplier_country,
            "Suppliers_currency": supplier.supplier_currency,
            "currency_conversion_rate": float(supplier.exchange_rate)
            if supplier.exchange_rate else 0,
            "Accessible_Dangerous_Goods": str(
                bool(supplier.accessible_dangerous_goods)
            ),
            "materials": [],
        }

        for item in supplier_items_map.get(
            supplier.supplier_quotation_id, []
        ):
            s_json["materials"].append({
                "material_no": item.material_no,
                "material_description": item.material_description,
                "weight_of_package": item.weight_of_package,
                "dim_of_package": item.dim_of_package,
                "lead_time": item.lead_time,
                "price_per_unit": float(item.price_per_unit)
                if item.price_per_unit else None,
                "HSN_code": item.hsn_code,
                "offered_quantity": float(item.offered_quantity)
                if item.offered_quantity else None,
            })

        result.append(s_json)

    return result

def build_bank_charges(rows_or_static: any, supplier_exchange_rate=None):
    """
    Build bank charges from static dict (new) or ORM rows (legacy).
    
    UPDATED: Now accepts static charge dict from static_charges.py
    Falls back to legacy behavior if rows are passed.
    """
    # Check if input is static format (dict with charge fields)
    if isinstance(rows_or_static, dict):
        return build_bank_charges_from_static(rows_or_static, supplier_exchange_rate)
    
    # Legacy: accept ORM rows
    rows = rows_or_static
    if not rows:
        return []

    result = {
        "DBS_percentage": None,
        "commission_charges": None,
        "cable_charges": None,
    }

    for row in rows:
        name = row.charge_name.lower()

        if ("dbs" in name or "bank commission" in name) and row.amount_type == "percentage":
            result["DBS_percentage"] = float(row.amount) / 100

        elif ("commission" in name) and row.amount_type == "fixed":
            result["commission_charges"] = float(row.amount)

        elif "cable" in name and row.amount_type == "fixed":
            result["cable_charges"] = float(row.amount)

    return [{k: v for k, v in result.items() if v is not None}]


def derive_local_shipment_type(suppliers):
    """
    Derive local shipment type from primary supplier (suppliers[0]).

    Fallback:
        "safe_express"
    """

    if not suppliers:
        return "safe_express"

    primary = suppliers[0]

    if primary.local_delivery_partner_type:
        return primary.local_delivery_partner_type.lower().replace(" ", "_")

    return "safe_express"

def build_consolidated_local_freight_charges(rows_or_static, delivery_category, suppliers):
    """
    Build ONE consolidated local freight pricing object
    for a given delivery category (static or legacy).

    Includes:
    - DTDC Priority (route-based)
    - DTDC Safe Express (route-based)
    - Safe Express risk charges (All Routes)
    - BlueDart Express (all routes)

    Shipment type is derived from SupplierQuotation (supplier[0]).
    
    UPDATED: Now accepts static tariff list or ORM rows
    """
    
    # Check if input is static format (list of tariff dicts)
    if isinstance(rows_or_static, list) and rows_or_static and isinstance(rows_or_static[0], dict):
        # Static format: already has all needed fields
        rows = rows_or_static
        is_static = True
    else:
        # Legacy ORM format
        rows = rows_or_static
        is_static = False

    if not rows:
        return {}

    SLAB_FIELD_MAP = {
        "upto_500g": "upto_half_kg",
        "add_500g": "additional_per_half_kg",
        "per_kg_gt_10kg": "per_kg_after_10_kg",
        "upto_3kg": "upto_3kg",
        "gt_3kg": "per_kg_after_3_kg",

        "fuel_surcharge_percent": "fuel_surcharge_percentage",
        "risk_surcharge_percent": "risk_surcharge_percentage",
        "risk_on_value_percentage": "risk_on_value_percentage",
        "risk_min_charge": "risk_surcharge_min",
        "freight_min": "freight_min",
        "min_charge_percentage": "freight_percentage",
        "CAF_percent": "currency_adjustment_factor_percentage",
        "non_document_charge": "non_document_charge",
        "risk_charge": "risk_charge",
        "gst_percentage": "gst_percentage",
    }

    shipment_type = derive_local_shipment_type(suppliers) or "safe_express"

    result = {
        "local_delivery_partner": "dtdc",
        "shipment_type": shipment_type,
        "delivery_category": delivery_category.lower(),
    }

    for row in rows:
        if is_static:
            # Static format is already a dict
            carrier = row.get("local_delivery_partner", "").lower()
            service = row.get("shipment_type", "").lower()
            slab = None
            rate = None
        else:
            # Legacy ORM format
            carrier = (row.carrier or "").lower()
            service = (row.service_type or "").lower().replace(" ", "_")
            slab = row.weight_slab
            rate = float(row.rate) if row.rate is not None else None

        # ===================== DTDC =====================
        if carrier == "dtdc":
            # For static format, iterate through the dict
            if is_static:
                for field_name, field_value in row.items():
                    if field_name in ["local_delivery_partner", "shipment_type", "delivery_category"]:
                        continue
                    
                    if isinstance(field_value, (int, float)):
                        result[field_name] = field_value
            else:
                # Legacy: use slab mapping
                if slab in (
                    "upto_500g",
                    "add_500g",
                    "per_kg_gt_10kg",
                    "upto_3kg",
                    "gt_3kg",
                ):
                    mapped_field = SLAB_FIELD_MAP.get(slab)
                    result[mapped_field] = rate

                # ---------- Fuel surcharge ----------
                elif slab == "fuel_surcharge_percent":
                    result["dtdc_fuel_surcharge_percentage"] = rate

                # ---------- SAFE EXPRESS risk ----------
                elif service == "safe_express" and slab in (
                    "risk_surcharge_percent",
                    "risk_min_charge",
                ):
                    mapped_field = SLAB_FIELD_MAP.get(slab)
                    result[mapped_field] = rate
                elif carrier == "dtdc" and slab in (
                    "risk_on_value_percentage"
                ):
                    # Add service-specific suffix
                    service_suffix = service  # safe_express / priority

                    key = f"{SLAB_FIELD_MAP.get(slab)}_{service_suffix}"

                    result[key] = rate

        # ===================== BLUEDART =====================
        elif carrier == "bluedart":
            if is_static:
                # Static: copy all numeric fields
                for field_name, field_value in row.items():
                    if field_name in ["local_delivery_partner", "shipment_type", "delivery_category"]:
                        continue
                    if isinstance(field_value, (int, float)):
                        result[field_name] = field_value
            else:
                # Legacy: process slab mapping
                slab = row.weight_slab if hasattr(row, 'weight_slab') else None
                if slab == "freight_min":
                    result["bluedart_freight_min"] = rate
                elif slab == "min_charge_percentage":
                    result["bluedart_freight_percentage"] = rate
                elif slab == "fuel_surcharge_percent":
                    result["bluedart_fuel_surcharge_percentage"] = rate
                elif slab == "CAF_percent":
                    result["currency_adjustment_factor_percentage"] = rate
                elif slab == "non_document_charge":
                    result["bluedart_non_document_charge"] = rate
                elif slab == "risk_charge":
                    result["bluedart_risk_charge"] = rate
                elif slab == "gst_percentage":
                    result["gst_percentage"] = rate

    return result

def build_clearance_charges(rows_or_static: any):
    """
    Build clearance charges from static dict (new) or ORM rows (legacy).
    
    UPDATED: Now accepts static charge dict from static_charges.py
    Falls back to legacy behavior if rows are passed.
    """
    # Check if input is static format (dict with carrier keys)
    if isinstance(rows_or_static, dict) and any(k.upper() in rows_or_static for k in ["FEDEX", "UPS", "FF"]):
        return build_clearance_charges_from_static(rows_or_static)
    
    # Legacy: accept ORM rows
    rows = rows_or_static
    
    if not rows:
        logger.warning("No clearance charges found")
        return {}

    result = {}

    # --------------------------------------------------
    # Main loop
    # --------------------------------------------------
    for row in rows:
        carrier = row.carrier.upper()
        shipment = SHIPMENT_MAP.get(row.shipment_type)

        # -------- Guard case (only one) --------
        if not shipment:
            logger.warning("Unknown shipment type: %s", row.shipment_type)
            continue

        carrier_block = result.setdefault(carrier, {})
        shipment_block = carrier_block.setdefault(shipment, {})

        charge_name = row.charge_name.lower()

        # -------- Duty percentage --------
        if row.duty_percent is not None:
            shipment_block["duties_tax_percentage"] = fmt(row.duty_percent)

        # -------- Apply charge rules --------
        for rule in CHARGE_RULES:
            if any(key in charge_name for key in rule["match"]):
                if rule.get("use_min") and row.amount_min is not None:
                    shipment_block[rule["field"]] = fmt(row.amount_min)

                if rule.get("per_kg_field") and row.per_kg_rate is not None:
                    shipment_block[rule["per_kg_field"]] = fmt(row.per_kg_rate)

                break  # stop after first match

    return result

# def build_freight_charges(suppliers, other_charges_rows, total_weight):
#     """
#     Build ONE consolidated freight charge object containing all carrier data.
#     - FedEx / UPS charges remain carrier-specific
#     - Common charges (DG) apply globally
#     - Does NOT break existing functionality
#     """

#     # ---------------- Primary partner ----------------
#     primary_partner = None
#     if suppliers and suppliers[0].freight_delivery_partner:
#         primary_partner = suppliers[0].freight_delivery_partner.lower()

#     if not primary_partner:
#         logger.warning("No freight delivery partner found")
#         return []

#     freight = {
#         "freight_delivery_partner": primary_partner,
#         "accessible_dangerous_goods": bool(
#             getattr(suppliers[0], "accessible_dangerous_goods", False)
#         )
#     }

#     # ---------------- Iterate other charges ----------------
#     for charge_row in other_charges_rows:
#         carrier = (charge_row.carrier or "").upper()
#         category = (charge_row.charge_category or "").lower()
#         name = (charge_row.charge_name or "").lower()

#         amount = charge_row.amount
#         amount_type = charge_row.amount_type
#         condition_value = charge_row.condition_value

#         # =====================================================
#         # FUEL SURCHARGE (Carrier specific)
#         # =====================================================
#         if "fuel" in category or "fuel surcharge" in name:
#             if amount and amount_type == "percentage":
#                 if carrier == "FEDEX":
#                     freight["fedex_fuel_surcharge_percentage"] = float(amount)
#                 elif carrier == "UPS":
#                     freight["UPS_fuel_surcharge_percentage"] = float(amount)

#         # =====================================================
#         # DANGEROUS GOODS (COMMON – applies to all carriers)
#         # =====================================================
#         elif carrier == "COMMON" and (
#             "dangerous" in name or "dangerous_goods" in category
#         ):
#             if amount and amount_type == "fixed":
#                 freight["accessible_dangerous_goods_charge_min"] = int(float(amount))
#             elif amount and amount_type == "per_kg":
#                 freight["accessible_dangerous_goods_charge_per_kg"] = float(amount)

#         # =====================================================
#         # OVERSIZE (Carrier specific)
#         # =====================================================
#         elif "oversize" in category or "oversize" in name:
#             if carrier == "FEDEX":
#                 if amount and amount_type == "fixed":
#                     freight["fedex_oversize_charges"] = int(float(amount))
#                 if condition_value and ">" in condition_value:
#                     try:
#                         freight["fedex_oversize"] = int(
#                             float(condition_value.replace(">", "").replace("cm", "").strip())
#                         )
#                     except Exception:
#                         pass

#             elif carrier == "UPS":
#                 if amount and amount_type == "fixed":
#                     freight["UPS_oversize_charges"] = int(float(amount))
#                 if condition_value and ">" in condition_value:
#                     try:
#                         freight["UPS_oversize"] = int(
#                             float(condition_value.replace(">", "").replace("cm", "").strip())
#                         )
#                     except Exception:
#                         pass

#         # =====================================================
#         # SURGE FEE (UPS – route based)
#         # =====================================================
#         elif "surge" in category or "surge" in name:
#             if condition_value:
#                 freight["surge_fee_from_india_to"] = (
#                     condition_value.split("→")[-1]
#                     if "→" in condition_value
#                     else condition_value
#                 )
#             if amount:
#                 freight["surge_fee_amount"] = (
#                     int(float(amount))
#                     if float(amount).is_integer()
#                     else float(amount)
#                 )

#     # =====================================================
#     # BASE FREIGHT (Zone-based calculation)
#     # =====================================================
#     if primary_partner == "fedex":
#         fedex_calc = calculate_fedex_freight_charge(
#             origin_country=suppliers[0].supplier_country,
#             total_weight=total_weight
#         )
#         if fedex_calc:
#             freight["zone"] = fedex_calc.get("zone")
#             freight["base_freight_charge"] = fedex_calc.get("amount")

#     return [freight]

def build_freight_charges(
    suppliers,
    other_charges_rows,
    total_weight,
    return_default_if_missing: bool = False,
):
    """
    New logic, OLD response structure.
    freight_charges -> [ { single consolidated object } ]
    """

    # ---------------- Primary supplier ----------------
    primary_supplier = suppliers[0] if suppliers else None
    primary_partner = (
        primary_supplier.freight_delivery_partner.lower()
        if primary_supplier and primary_supplier.freight_delivery_partner
        else None
    )

    # ---------------- Allowed carriers ----------------
    if primary_partner:
        allowed_carriers = {primary_partner.upper()}
    else:
        allowed_carriers = (
            DEFAULT_FREIGHT_PARTNERS
            if return_default_if_missing
            else ALL_FREIGHT_PARTNERS
        )

    allowed_with_common = allowed_carriers | {"COMMON"}

    # ---------------- SINGLE freight object (IMPORTANT) ----------------
    freight = {
        "freight_delivery_partner": primary_partner,
        "accessible_dangerous_goods": bool(
            getattr(primary_supplier, "accessible_dangerous_goods", False)
        ),
    }

    # ---------------- Iterate charges ----------------
    for row in other_charges_rows:
        carrier = (row.carrier or "").upper()
        if carrier not in allowed_with_common:
            continue

        category = (row.charge_category or "").lower()
        name = (row.charge_name or "").lower()
        amount = row.amount
        amount_type = row.amount_type
        condition_value = row.condition_value

        # =====================================================
        # FUEL SURCHARGE (Carrier specific)
        # =====================================================
        if "fuel" in category or "fuel surcharge" in name:
            if amount and amount_type == "percentage":
                if carrier == "FEDEX":
                    freight["fedex_fuel_surcharge_percentage"] = float(amount)
                elif carrier == "UPS":
                    freight["UPS_fuel_surcharge_percentage"] = float(amount)

        # =====================================================
        # DANGEROUS GOODS (COMMON)
        # =====================================================
        elif carrier == "COMMON" and (
            "dangerous" in name or "dangerous_goods" in category
        ):
            if amount and amount_type == "fixed":
                freight["accessible_dangerous_goods_charge_min"] = int(float(amount))
            elif amount and amount_type == "per_kg":
                freight["accessible_dangerous_goods_charge_per_kg"] = float(amount)

        # =====================================================
        # OVERSIZE (Carrier specific)
        # =====================================================
        elif "oversize" in category or "oversize" in name:
            if carrier == "FEDEX":
                if amount and amount_type == "fixed":
                    freight["fedex_oversize_charges"] = int(float(amount))
                if condition_value and ">" in condition_value:
                    try:
                        freight["fedex_oversize"] = int(
                            float(
                                condition_value.replace(">", "")
                                .replace("cm", "")
                                .strip()
                            )
                        )
                    except Exception:
                        pass

            elif carrier == "UPS":
                if amount and amount_type == "fixed":
                    freight["UPS_oversize_charges"] = int(float(amount))
                if condition_value and ">" in condition_value:
                    try:
                        freight["UPS_oversize"] = int(
                            float(
                                condition_value.replace(">", "")
                                .replace("cm", "")
                                .strip()
                            )
                        )
                    except Exception:
                        pass

        # =====================================================
        # SURGE FEE (UPS)
        # =====================================================
        elif "surge" in category or "surge" in name:
            if condition_value:
                freight["surge_fee_from_india_to"] = (
                    condition_value.split("→")[-1]
                    if "→" in condition_value
                    else condition_value
                )
            if amount:
                freight["surge_fee_amount"] = (
                    int(float(amount))
                    if float(amount).is_integer()
                    else float(amount)
                )

    # =====================================================
    # BASE FREIGHT (FedEx only – as before)
    # =====================================================
    if primary_partner == "fedex":
        fedex_calc = calculate_fedex_freight_charge(
            origin_country=primary_supplier.supplier_country,
            total_weight=total_weight,
        )
        if fedex_calc:
            freight["zone"] = fedex_calc.get("zone")
            freight["base_freight_charge"] = fedex_calc.get("amount")

    return [freight]

def adapt_clearance_charges(raw_clearance: dict, suppliers, delivery_type) -> list:
    """
    Adapt clearance charges into REQUIRED API format.
    clearance_shipment_type is added at GLOBAL level.
    """

    if not raw_clearance:
        return []

    final_block = {}

    # ---------------- GLOBAL clearance shipment type ----------------
    clearance_shipment_type = derive_clearance_shipment_type(
        suppliers, delivery_type
    )

    if clearance_shipment_type:
        final_block["clearance_shipment_type"] = clearance_shipment_type
    # ---------------- Carrier-wise blocks ----------------
    for carrier, shipment_map in raw_clearance.items():
        carrier_upper = carrier.upper()

        if carrier_upper == "FEDEX":
            fedex_obj = {}
            if "LTL" in shipment_map:
                fedex_obj["LTL"] = [shipment_map["LTL"]]
            if "GTL" in shipment_map:
                fedex_obj["GTL"] = [shipment_map["GTL"]]

            final_block["fedex"] = [fedex_obj]

        elif carrier_upper == "UPS":
            ups_obj = {}
            if "LTL" in shipment_map:
                ups_obj["LTL"] = [shipment_map["LTL"]]
            if "GTL" in shipment_map:
                ups_obj["GTL"] = [shipment_map["GTL"]]

            final_block["UPS"] = [ups_obj]

        elif carrier_upper == "FF":
            ff_obj = {}
            for charges in shipment_map.values():
                ff_obj.update(charges)

            final_block["freight_forwarder"] = [ff_obj]

    return [final_block]




def extract_manufacturer_product_no(mapping_json):
    """
    Extract manufacturer_product_name from RFQLineItems.mapping_json
    Supports JSON column (list/dict).
    """

    if not mapping_json:
        return None

    # Case 1: mapping_json is already a list
    if isinstance(mapping_json, list) and mapping_json:
        return mapping_json[0].get("manufacturer_product_name")

    # Case 2: mapping_json is a dict
    if isinstance(mapping_json, dict):
        return mapping_json.get("manufacturer_product_name")

    return None

# --------------------------------------------------
# ENDPOINT
# --------------------------------------------------

@calculation_engine_routes.route("/build-json", methods=["POST"])
def build_engine_json():
    try:
        payload = request.get_json(force=True)
        sys_rfq_id = payload["sys_rfq_id"]
        return_all_data = payload.get("return_all_data", True)
        # UPDATED: Support agent overrides for this request
        charge_overrides = payload.get("charge_overrides", {})

        # UPDATED: Create session ID for this calculation (scoped to request)
        session_id = f"rfq-{sys_rfq_id}-{uuid.uuid4().hex[:8]}"

        logger.info(
            "Engine JSON started | RFQ=%s | session=%s | return_all_data=%s",
            sys_rfq_id, session_id, return_all_data
        )

        # UPDATED: Apply charge overrides if provided by agent
        if charge_overrides:
            logger.info("Applying charge overrides for session: %s", session_id)
            override_charges(session_id, charge_overrides)

        # Get charges (static + any overrides for this session)
        charges_data = get_charges(session_id)

        # ---------------- RFQ ----------------
        rfq = get_rfq(sys_rfq_id)
        rfq_items = get_rfq_items(sys_rfq_id)

        # ---------------- Suppliers ----------------
        suppliers = get_suppliers(sys_rfq_id)
        if not suppliers:
            return jsonify({"error": "No suppliers found"}), 400

        supplier_items_map = {}
        all_supplier_items = []

        for s in suppliers:
            items = get_supplier_items(s.supplier_quotation_id)
            supplier_items_map[s.supplier_quotation_id] = items
            all_supplier_items.extend(items)

        # ---------------- Derived ----------------
        total_weight = derive_total_shipment_weight(all_supplier_items)
        raw_category = derive_delivery_category(rfq)
        mapped_category = LOCAL_ROUTE_TYPE_MAP.get(raw_category)

        logger.info(
            "Derived | weight=%s | category=%s → %s",
            total_weight, raw_category, mapped_category
        )

        # UPDATED: Use static charges instead of DB queries
        # Build bank charges from static data
        bank_charges = build_bank_charges_from_static(
            charges_data.get("bank", {}),
            supplier_exchange_rate=suppliers[0].exchange_rate
        )

        delivery_type = derive_delivery_type(suppliers) or "local"

        # UPDATED: Use static clearance charges
        raw_clearance = build_clearance_charges_from_static(
            charges_data.get("clearance", {})
        )
        clearance_charges = adapt_clearance_charges(raw_clearance, suppliers, delivery_type)

        # UPDATED: Use static local freight charges
        local_freight_rows = build_local_freight_charges_from_static(
            charges_data.get("local", {}),
            raw_category
        )

        local_freight_charges = [
            build_consolidated_local_freight_charges(
                local_freight_rows,
                raw_category,
                suppliers
            )
        ]

        primary = suppliers[0]

        # UPDATED: Use static other charges
        other_charges_rows = []
        if primary.freight_delivery_partner:
            other_charges_rows.extend(
                build_other_charges_from_static(
                    charges_data.get("other", {}),
                    primary.freight_delivery_partner
                )
            )

        # Add other carriers if return_all_data is true
        if return_all_data:
            for carrier_name in ["FEDEX", "UPS", "COMMON"]:
                try:
                    other_charges_rows.extend(
                        build_other_charges_from_static(
                            charges_data.get("other", {}),
                            carrier_name
                        )
                    )
                except Exception as e:
                    logger.debug(f"No other charges for {carrier_name}: {e}")

        # UPDATED: Build freight charges (still uses DB for rate slabs, but supports overrides)
        freight_charges = build_freight_charges(
            suppliers, other_charges_rows, total_weight
        )

        # ---------------- Final JSON ----------------
        final_json = {
            "priority":["lead_time", "price", "quantity"],
            'no_of_quotations':3,
            "customer": [{
                "rfq_no": rfq.sys_rfq_id,
                "customer_name": rfq.customer_name,
                "customer_email": rfq.customer_email,
            }],
            "materials": [
                {
                    "material_no": (
                        extract_manufacturer_product_no(i.mapping_json)
                        or i.customer_part_number
                    ),
                    "material_description": i.product_description,
                    "ordered_quantity": float(i.quantity),
                }
                for i in rfq_items
            ],
            "suppliers": build_suppliers_json(
                suppliers, supplier_items_map
            ),
            "charges": [{
                "delivery_type": delivery_type,
                "freight_charges": freight_charges,
                "local_freight_charges": local_freight_charges,
                "bank_charges": bank_charges,
                "clearance_charges": clearance_charges,
            }]
            # "derived": {
            #     "total_weight": total_weight,
            #     "delivery_category": raw_category,
            #     "zone": zone.zone_code if zone else None,
            # },
        }

        logger.info("Engine JSON completed | RFQ=%s", sys_rfq_id)
        return jsonify(final_json), 200

    except KeyError:
        logger.exception("sys_rfq_id missing")
        return jsonify({"error": "sys_rfq_id is required"}), 400

    except Exception:
        logger.exception("Engine JSON build failed")
        return jsonify({"error": "Internal server error"}), 500


    


import re
from fuzzywuzzy import process, fuzz
from flask import request, jsonify

# ---------------------------
# Utility Functions
# ---------------------------

def extract_weight(value):
    """Extract first numeric value from a string."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    match = re.search(r"(\d+(\.\d+)?)", str(value))
    return float(match.group(1)) if match else None


def normalize_country(text):
    if not text:
        return ""
    text = re.sub(r"[^A-Za-z\s]", "", text)
    return text.strip().lower()

def fuzzy_country_match(input_country, valid_countries, threshold=90):
    """
    Returns best matched country if score >= threshold, else None
    """

    if not input_country or not valid_countries:
        return None

    # 🔹 Short inputs need lower threshold
    effective_threshold = threshold
    if len(input_country) <= 4:
        effective_threshold = 60
    elif len(input_country) <= 7:
        effective_threshold = 70

    match = process.extractOne(
        input_country,
        valid_countries,
        scorer=fuzz.partial_ratio   # 🔥 better for missing words
    )

    if not match:
        return None

    country, score = match[0], match[1]

    return country if score >= effective_threshold else None

# ---------------------------
# API Route
# ---------------------------

def match_ups_weight_slab(weight_slab, chargeable_weight):
    if not weight_slab:
        return False

    slab = weight_slab.strip().lower()

    # 1️⃣ 1000+ case
    if slab.endswith("+"):
        try:
            min_w = float(slab.replace("+", ""))
            return chargeable_weight >= min_w
        except ValueError:
            return False

    # 2️⃣ Range case (21-44)
    if "-" in slab:
        try:
            min_w, max_w = map(float, slab.split("-"))
            return min_w <= chargeable_weight <= max_w
        except ValueError:
            return False

    # 3️⃣ Extract full numeric value safely (Doc 0.5, NDC 0.5, 1, 1.5)
    numbers = re.findall(r"\d+(?:\.\d+)?", slab)
    if numbers:
        try:
            return float(numbers[0]) == chargeable_weight
        except ValueError:
            return False

    # 4️⃣ LTR / Doc without number → document shipment
    if slab in {"ltr", "doc"}:
        return chargeable_weight <= 0.5

    return False


@calculation_engine_routes.route("/getfreightcharges", methods=["POST"])
def get_freight_charges():
    session = next(db_session())
    try:
        payload = request.get_json(force=True)

        carrier = (payload.get("freight_delivery_partner") or "").lower()
        raw_country = payload.get("country")

        chargeable_weight = extract_weight(payload.get("chargable_weight"))
        print(f"QQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ-------------------{chargeable_weight}")
        
        if not carrier or not raw_country or chargeable_weight is None or chargeable_weight < 0:
            return jsonify({"error": "Invalid payload"}), 400

        # ---------------------------
        # FUZZY COUNTRY MATCH
        # ---------------------------

        country_input = normalize_country(raw_country)
        valid_countries = []

        if carrier == "fedex":
            valid_countries = [
                normalize_country(r[0])
                for r in session.query(
                    FedexOriginZoneConfig.origin_country
                ).filter(
                    FedexOriginZoneConfig.del_flg == False
                ).distinct().all()
            ]

        elif carrier == "ups":
            valid_countries = [
                normalize_country(r[0])
                for r in session.query(
                    UPSOriginZoneConfig.destination_country
                ).filter(
                    UPSOriginZoneConfig.del_flg == False
                ).distinct().all()
            ]

        logger.info("Country input: %s", country_input)
        logger.info("Valid countries sample: %s", valid_countries[:10])

        country_db = fuzzy_country_match(
            country_input,
            valid_countries,
            threshold=90
        )
        print(f"ttttttttttttttttttttt--------------------{country_db}")

        # Fix #3: Return a clear error instead of silently using the wrong country.
        if not country_db:
            logger.warning(
                "Country '%s' not recognized for carrier '%s'.",
                raw_country, carrier
            )
            if not valid_countries:
                return jsonify({"error": "No countries configured for carrier"}), 400
            return jsonify({
                "error": f"Country '{raw_country}' is not recognized for carrier '{carrier}'. "
                         "Please provide a valid origin country name.",
                "sample_valid_countries": valid_countries[:10],
            }), 400

        # ---------------------------
        # FEDEX
        # ---------------------------

        if carrier == "fedex":
            zone = (
                session.query(FedexOriginZoneConfig)
                .filter(
                    func.lower(FedexOriginZoneConfig.origin_country) == country_db,
                    FedexOriginZoneConfig.del_flg == False
                )
                .first()
            )

            if not zone:
                logger.warning(
                    "No zone found for country '%s' on carrier 'fedex'. Returning base freight charge.",
                    country_db
                )
                # 🔄 FALLBACK: Return base charge when zone not found
                return jsonify({
                    "carrier": "fedex",
                    "country": country_db,
                    "zone": "DEFAULT",
                    "chargeable_weight": chargeable_weight,
                    "freight_charge": 0.0,  # Base charge when zone not available
                    "note": "Using default zone - exact zone not found"
                }), 200

            zone_column = f"zone_{zone.zone_code.lower()}"
            print(f"POPOPOIUOIUOIYOIYOIOIPPPPPPPPPPP-------------------{zone_column}")
            freight = (
                session.query(FedexFreightCharge)
                .filter(
                    FedexFreightCharge.weight_kg >= chargeable_weight,
                    FedexFreightCharge.del_flg == False
                )
                .order_by(FedexFreightCharge.weight_kg.asc())
                .first()
            )

            if not freight:
                logger.warning(
                    "No freight charge found for weight %.2f kg on carrier 'fedex' zone '%s'. Returning base charge.",
                    chargeable_weight, zone.zone_code
                )
                # 🔄 FALLBACK: Return base charge when weight slab not found
                return jsonify({
                    "carrier": "fedex",
                    "country": country_db,
                    "zone": zone.zone_code,
                    "chargeable_weight": chargeable_weight,
                    "freight_charge": 0.0,  # Base charge when weight slab not found
                    "note": "Using base charge - weight slab not found"
                }), 200

            charge = getattr(freight, zone_column, None)

            if charge is None:
                logger.warning(
                    "No freight charge defined for zone '%s' on carrier 'fedex'. Returning base charge.",
                    zone.zone_code
                )
                # 🔄 FALLBACK: Return base charge when zone column missing
                return jsonify({
                    "carrier": "fedex",
                    "country": country_db,
                    "zone": zone.zone_code,
                    "chargeable_weight": chargeable_weight,
                    "freight_charge": 0.0,  # Base charge when zone column missing
                    "note": "Using base charge - zone column not defined"
                }), 200

            return jsonify({
                "carrier": "fedex",
                "country": country_db,
                "zone": zone.zone_code,
                "chargeable_weight": chargeable_weight,
                "freight_charge": float(charge),
                "amount": float(charge),   # Fix #1: alias for extract_amount=True
            }), 200

        # ---------------------------
        # UPS
        # ---------------------------
        elif carrier == "ups":
            zone = (
                session.query(UPSOriginZoneConfig)
                .filter(
                    func.lower(UPSOriginZoneConfig.destination_country)
                    .like(func.lower(country_db) + "%"),   # ✅ matches Brazil*
                    UPSOriginZoneConfig.del_flg == False
                )
                .first()
            )
            if not zone:
                logger.warning(
                    "No zone found for country '%s' on carrier 'ups'. Returning base freight charge.",
                    country_db
                )
                # 🔄 FALLBACK: Return base charge when zone not found
                return jsonify({
                    "carrier": "ups",
                    "country": country_db,
                    "zone": "DEFAULT",
                    "chargeable_weight": chargeable_weight,
                    "freight_charge": 0.0,  # Base charge when zone not available
                    "note": "Using default zone - exact zone not found"
                }), 200

            zone_column = f"zone_{zone.zone_code.lower()}"

            freight_rows = (
                session.query(UPSFreightCharge)
                .filter(UPSFreightCharge.del_flg == False)
                .all()
            )

            matched_freight = None

            for f in freight_rows:
                if match_ups_weight_slab(f.weight_slab, chargeable_weight):
                    matched_freight = f
                    break

            if not matched_freight:
                logger.warning(
                    "No freight charge found for weight %.2f kg on carrier 'ups' zone '%s'. Returning base charge.",
                    chargeable_weight, zone.zone_code
                )
                # 🔄 FALLBACK: Return base charge when weight slab not found
                return jsonify({
                    "carrier": "ups",
                    "country": country_db,
                    "zone": zone.zone_code,
                    "chargeable_weight": chargeable_weight,
                    "freight_charge": 0.0,  # Base charge when weight slab not found
                    "note": "Using base charge - weight slab not found"
                }), 200

            charge = getattr(matched_freight, zone_column, None)

            if charge is None:
                logger.warning(
                    "No freight charge defined for zone '%s' on carrier 'ups'. Returning base charge.",
                    zone.zone_code
                )
                # 🔄 FALLBACK: Return base charge when zone column missing
                return jsonify({
                    "carrier": "ups",
                    "country": country_db,
                    "zone": zone.zone_code,
                    "chargeable_weight": chargeable_weight,
                    "freight_charge": 0.0,  # Base charge when zone column missing
                    "note": "Using base charge - zone column not defined"
                }), 200

            return jsonify({
                "carrier": "ups",
                "country": country_db,
                "zone": zone.zone_code,
                "chargeable_weight": chargeable_weight,
                "freight_charge": float(charge),
                "amount": float(charge),   # Fix #1: alias for extract_amount=True
            }), 200

        return jsonify({"error": "Unsupported carrier"}), 400

    finally:
        session.close()


# --------------------------------------------------
# Lightweight charge endpoints for MCP tools
# --------------------------------------------------


@calculation_engine_routes.route("/local_charges", methods=["POST"])
def get_local_charges_api():
    payload = request.get_json(force=True)
    category = payload.get("delivery_category")
    carrier = payload.get("carrier")

    # Optional computation params — if provided we return a calculated amount
    invoice_value  = float(payload.get("invoice_value") or 0.0)
    weight_kg      = float(payload.get("weight_kg") or 0.0)
    zone_multiplier = float(payload.get("zone_multiplier") or 1.0)

    if not category:
        return jsonify({"error": "delivery_category is required"}), 400

    # Use static charges instead of database
    charges_data = get_charges()
    local_freight = charges_data.get("local", {})
    charges = build_local_freight_charges_from_static(local_freight, category)

    if carrier:
        # Normalize names so values like "Blue Dart Express" can still match
        # stored partners like "bluedart".
        norm = lambda s: re.sub(r"[^a-z0-9]+", "", (s or "").lower())
        carrier_norm = norm(carrier)
        filtered = [
            c for c in charges
            if carrier_norm and (
                carrier_norm in norm(c.get("local_delivery_partner", ""))
                or norm(c.get("local_delivery_partner", "")) in carrier_norm
            )
        ]
        charges = filtered or charges

    # ------------------------------------------------------------------
    # If caller provided invoice_value + weight_kg, compute amounts now
    # so the MCP extract_amount=True path can pick up a numeric "amount".
    # ------------------------------------------------------------------
    if invoice_value > 0 and weight_kg > 0 and charges:
        computed_rows = []
        for tariff in charges:
            try:
                amt = calculate_local_freight_amount(
                    tariff, weight_kg, invoice_value, zone_multiplier
                )
            except Exception as exc:
                logger.warning("calculate_local_freight_amount failed: %s", exc)
                amt = 0.0
            computed_rows.append({
                "local_delivery_partner": tariff.get("local_delivery_partner"),
                "shipment_type": tariff.get("shipment_type"),
                "delivery_category": tariff.get("delivery_category"),
                "amount": amt,
            })

        # If exactly one carrier returned, expose top-level "amount" so
        # _post_charge(extract_amount=True) can find it without parsing the list.
        top_amount = computed_rows[0]["amount"] if len(computed_rows) == 1 else None
        response = {
            "delivery_category": category,
            "charges": computed_rows,
        }
        if top_amount is not None:
            response["amount"] = top_amount
        return jsonify(response), 200

    return jsonify({"delivery_category": category, "charges": charges if charges else []}), 200


@calculation_engine_routes.route("/clearance_charges", methods=["POST"])
def get_clearance_charges_api():
    payload = request.get_json(force=True)
    carrier = payload.get("carrier")
    if not carrier:
        return jsonify({"error": "carrier is required"}), 400

    # Use static charges instead of database
    charges_data = get_charges()
    clearance_data = charges_data.get("clearance", {})
    charges = build_clearance_charges_from_static(clearance_data)
    return jsonify({"carrier": carrier, "charges": charges.get(carrier.upper(), {})}), 200


@calculation_engine_routes.route("/bank_charges", methods=["POST"])
def get_bank_charges_api():
    payload = request.get_json(force=True)
    supplier_exchange_rate = payload.get("exchange_rate")

    # Use static charges instead of database
    charges_data = get_charges()
    bank_data = charges_data.get("bank", {})
    charges = build_bank_charges_from_static(bank_data, supplier_exchange_rate=supplier_exchange_rate)
    return jsonify({"charges": charges}), 200


@calculation_engine_routes.route("/other_surcharges", methods=["POST"])
def get_other_surcharges_api():
    payload = request.get_json(force=True)
    carrier = payload.get("carrier")
    if not carrier:
        return jsonify({"error": "carrier is required"}), 400

    # Use static charges instead of database
    charges_data = get_charges()
    other_data = charges_data.get("other", {})
    data = build_other_charges_from_static(other_data, carrier)

    return jsonify({"carrier": carrier, "surcharges": data}), 200


@calculation_engine_routes.route("/quote_totalizer", methods=["POST"])
def quote_totalizer_api():
    payload = request.get_json(force=True)

    if "base_amount" not in payload:
        return jsonify({"error": "base_amount is required"}), 400

    base = float(payload.get("base_amount") or 0)
    charges_input = payload.get("charges", [])
    margin_percent = payload.get("margin_percent")
    margin_amount = payload.get("margin_amount")

    def _safe_float(v):
        """Coerce a value to float; skip dicts/lists/non-numerics."""
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
        return 0.0  # dicts, lists, None, unparseable strings → 0

    total_charges = 0.0
    if isinstance(charges_input, dict):
        total_charges = sum(_safe_float(v) for v in charges_input.values())
    elif isinstance(charges_input, list):
        total_charges = sum(_safe_float(v) for v in charges_input)

    subtotal = base + total_charges

    if margin_amount is not None:
        margin = float(margin_amount)
    elif margin_percent is not None:
        margin = subtotal * (float(margin_percent) / 100.0)
    else:
        margin = 0.0

    grand_total = subtotal + margin

    return jsonify({
        "base_amount": fmt(base),
        "charges_total": fmt(total_charges),
        "margin": fmt(margin),
        "grand_total": fmt(grand_total),
        "amount": grand_total,  # Fix #1: numeric alias for extract_amount=True
    }), 200


def build_local_freight_charges(rows_or_static: any, delivery_category):
    """
    Build local freight tariff per carrier/service/route (static or legacy).
    
    UPDATED: Now accepts static charge list from static_charges_adapter
    Falls back to legacy behavior if ORM rows are passed.
    """
    # Check if input is static format (list of dicts with tariff structure)
    if isinstance(rows_or_static, list) and rows_or_static and isinstance(rows_or_static[0], dict):
        # Already in static adapter format
        return rows_or_static
    
    # Legacy: accept ORM rows
    rows = rows_or_static
    
    if not rows:
        logger.warning("No local freight charges matched")
        return []

    WEIGHT_SLAB_MAP = {
        "upto_500g": "upto_half_kg",
        "add_500g": "additional_per_half_kg",
        "per_kg_gt_10kg": "per_kg_after_10_kg",
        "upto_3kg": "upto_3kg",
        "gt_3kg": "per_kg_after_3_kg",
        "per_kg_gt_3kg": "per_kg_after_3_kg",
        "fuel_surcharge_percent": "fuel_surcharge_percentage",
        "risk_surcharge_percent": "risk_surcharge_percentage",
        "risk_on_value_percentage": "risk_on_value_percentage",
        "risk_min_charge": "risk_surcharge_min",
        "freight_min": "freight_min",
        "min_charge_percentage": "freight_percentage",
        "CAF_percent": "currency_adjustment_factor_percentage",
        "non_document_charge": "non_document_charge",
        "risk_charge": "risk_charge",
        "gst_percentage": "gst_percentage",
        "route_multiplier": "route_multiplier",
        "volumetric_divisor": "volumetric_divisor",
    }

    grouped = {}

    for row in rows:
        key = (
            row.carrier.lower(),
            row.service_type,
            delivery_category,
        )

        if key not in grouped:
            grouped[key] = {
                "local_delivery_partner": row.carrier.lower(),
                "shipment_type": row.service_type,
                "delivery_category": delivery_category,
            }

        slab_key = WEIGHT_SLAB_MAP.get(row.weight_slab)
        if slab_key:
            grouped[key][slab_key] = float(row.rate)

    return list(grouped.values())
