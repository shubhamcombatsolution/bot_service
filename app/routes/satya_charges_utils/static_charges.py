"""
static_charges.py
=================
All charges stored as plain Python dicts — no DB required.
The agent tool calls `override_charges(session_id, overrides)` to patch
any value for a single session.  `get_charges(session_id)` returns the
merged (static + override) charge set.

Usage in calculation_engine_routes.py
--------------------------------------
from static_charges import get_charges, override_charges, clear_overrides

# Agent tool calls this when the user provides a charge value:
override_charges(session_id, {"FEDEX": {"clearance": {"LTL": {"advancement_charge": 900}}}})

# Every builder function calls this instead of the DB:
charges = get_charges(session_id)
fedex_ltl = charges["FEDEX"]["clearance"]["LTL"]
"""

import copy
import threading

# ─────────────────────────────────────────────────────────────────────────────
# 1.  STATIC CHARGE TABLES  (sourced from Excel files & Erp_Configuration_RFQ)
# ─────────────────────────────────────────────────────────────────────────────

# ------------------------------------------------------------------
# 1A.  CLEARANCE CHARGES  (Erp_Configuration_RFQ → Customs Clearance)
# ------------------------------------------------------------------
# Conditions:
#   carrier  : "FEDEX" | "UPS" | "FF"  (freight-forwarder)
#   shipment : "LTL"  (courier_lt_1_lakh) | "GTL" (cargo_gt_1_lakh)
#   For FF only GTL-equivalent rows exist (no courier mode)
#
# Fields that are per-kg also carry a _per_kg sibling.
# duties_tax_percentage : 2 % on the customs-cleared invoice value.

STATIC_CLEARANCE_CHARGES = {
    # ── FEDEX ────────────────────────────────────────────────────────────
    "FEDEX": {
        # Courier mode  (invoice < 1 lakh INR)
        "LTL": {
            "duties_tax_percentage": "0.02",           # 2 %
            "advancement_charge": "800.00",            # min INR 800 or 2 % whichever > (use duties_tax for %)
            "courier_handling_charges": "356.00",
            "courier_handling_charges_per_kg": "10.79",
        },
        # Cargo mode  (invoice ≥ 1 lakh INR)
        "GTL": {
            "duties_tax_percentage": "0.02",
            "advancement_charge": "800.00",
            "formal_boe_charge": "1800.00",
            "TSP_general_charge": "223.00",
            "TSP_general_charge_prise_per_kg": "9.61",
            "TSP_special_cargo_charge": "445.00",
            "TSP_special_cargo_charge_prise_per_kg": "19.22",
            "demurrage_charges_General": "598.00",
            "demurrage_charges_General_prise_per_kg": "2.95",
            "demurrage_special_cargo_charges": "1113.00",
            "demurrage_special_cargo_charges_prise_per_kg": "10.97",
            "documentation_charge_per_AWB": "200.00",
        },
    },

    # ── UPS ──────────────────────────────────────────────────────────────
    "UPS": {
        # Courier mode
        "LTL": {
            "duties_tax_percentage": "0.02",
            "advancement_charge": "788.00",            # UPS uses 788, not 800
            "courier_handling_charges": "356.00",
            "courier_handling_charges_per_kg": "10.79",
        },
        # Cargo mode
        "GTL": {
            "duties_tax_percentage": "0.02",
            "advancement_charge": "800.00",
            "formal_boe_charge": "1800.00",
            "TSP_general_charge": "223.00",
            "TSP_general_charge_prise_per_kg": "9.61",
            "TSP_special_cargo_charge": "445.00",
            "TSP_special_cargo_charge_prise_per_kg": "19.22",
            "demurrage_charges_General": "598.00",
            "demurrage_charges_General_prise_per_kg": "2.95",
            "demurrage_special_cargo_charges": "1113.00",
            "demurrage_special_cargo_charges_prise_per_kg": "10.97",
            "documentation_charge_per_AWB": "200.00",
        },
    },

    # ── FREIGHT FORWARDER (FF) ───────────────────────────────────────────
    # Conditions: always cargo mode; transportation & DO Fee are extra.
    "FF": {
        "GTL": {
            "duties_tax_percentage": "0.02",
            "advancement_charge": "800.00",
            "formal_boe_charge": "2600.00",            # FF formal BOE is higher
            "TSP_general_charge": "223.00",
            "TSP_general_charge_prise_per_kg": "9.61",
            "TSP_special_cargo_charge": "445.00",
            "TSP_special_cargo_charge_prise_per_kg": "19.22",
            "demurrage_charges_General": "598.00",
            "demurrage_charges_General_prise_per_kg": "2.95",
            "demurrage_special_cargo_charges": "1113.00",
            "demurrage_special_cargo_charges_prise_per_kg": "10.97",
            "documentation_charge_per_AWB": "200.00",
            "transportation_charges": "2000.00",
            "DO_fee": "3575.00",
        },
    },
}


# ------------------------------------------------------------------
# 1B.  OTHER / FREIGHT SURCHARGES
#       (Fedex_freight.xlsx + UPS_Freight.xlsx)
# ------------------------------------------------------------------
# Conditions:
#   carrier            : "FEDEX" | "UPS" | "COMMON"
#   charge_category    : "fuel_surcharge" | "dangerous_goods" | "oversize" | "surge_fee"
#
# fuel_surcharge_percentage : multiplied against base freight.
# oversize_threshold_cm     : package longest-side > this → oversize charge applies.
# surge_fee rows give per-kg surcharge by destination group.

STATIC_OTHER_CHARGES = {
    "FEDEX": {
        # Fuel surcharge — check https://www.fedex.com/en-in/shipping/surcharges.html for current %.
        # As of March 2025 the published rate is 33.5 %.
        "fuel_surcharge_percentage": 0.335,

        # Oversize: longest dimension > 120 cm → flat INR 20,500
        "oversize_threshold_cm": 120,
        "oversize_charge_inr": 20500,
    },

    "UPS": {
        # Fuel surcharge — published at 32.5 %
        "fuel_surcharge_percentage": 0.325,

        # Oversize: longest dimension > 120 cm → flat INR 8,723
        "oversize_threshold_cm": 120,
        "oversize_charge_inr": 8723,

        # Surge fees (per-shipment, India origin)
        # Conditions: destination_group matches one of the keys below.
        "surge_fees": {
            "U.S":          38,    # India → U.S.
            "Europe":       43,    # India → Europe
            "Israel":       55,
            "China":        10,    # China Mainland, HK SAR, Macau SAR
            "Asia Pacific": 10,
        },
    },

    "COMMON": {
        # Accessible Dangerous Goods — applies to BOTH FedEx & UPS
        # Conditions: supplier.accessible_dangerous_goods == True
        "accessible_dangerous_goods_charge_min": 2750,   # INR minimum
        "accessible_dangerous_goods_charge_per_kg": 45,
    },
}


# ------------------------------------------------------------------
# 1C.  BANK CHARGES  (Erp_Configuration_RFQ → Forex Bank Charges)
# ------------------------------------------------------------------
# Conditions: always applied on global (forex) shipments.
# DBS_percentage    : applied on the foreign-currency invoice total.
# commission_charges: flat INR per transaction.
# cable_charges     : flat INR per wire transfer.

STATIC_BANK_CHARGES = {
    "DBS_percentage": 0.0025,    # 0.25 % bank commission
    "commission_charges": 500.0,
    "cable_charges": 500.0,
}


# ------------------------------------------------------------------
# 1D.  LOCAL FREIGHT CHARGES  (Local_freight.xlsx)
# ------------------------------------------------------------------
# Conditions:
#   carrier           : "dtdc" | "bluedart"
#   service_type      : "priority" | "safe_express" (DTDC only)
#   delivery_category : "Within City" | "Within State" | "Within Zone"
#                       | "Metros" | "Rest of india" | "Special destination"
#
# Weight slab logic (DTDC):
#   upto_half_kg      : base rate up to 500 g
#   additional_per_half_kg : per additional 500 g block
#   per_kg_after_10_kg: per kg once total > 10 kg
# Volumetric divisor  : 4750

STATIC_LOCAL_FREIGHT = {
    "dtdc": {
        "volumetric_divisor": 4750,

        # DTDC Priority  — weight slabs in INR
        "priority": {
            "Within City":        {"upto_half_kg": 25, "additional_per_half_kg": 15, "per_kg_after_10_kg": 26},
            "Within State":       {"upto_half_kg": 34, "additional_per_half_kg": 21, "per_kg_after_10_kg": 33},
            "Within Zone":        {"upto_half_kg": 38, "additional_per_half_kg": 27, "per_kg_after_10_kg": 45},
            "Metros":             {"upto_half_kg": 50, "additional_per_half_kg": 45, "per_kg_after_10_kg": 83},
            "Rest of india":      {"upto_half_kg": 55, "additional_per_half_kg": 50, "per_kg_after_10_kg": 90},
            "Special destination":{"upto_half_kg": 87, "additional_per_half_kg": 77, "per_kg_after_10_kg": 140},
            # Surcharges (apply on top of base freight)
            "fuel_surcharge_percentage": 0.10,          # 10 %
            "risk_on_value_percentage_priority": 0.001, # 0.1 % of invoice, min 50
            "risk_surcharge_min": 50,
        },

        # DTDC Safe Express  — weight slabs in INR
        "safe_express": {
            "Within City":        {"upto_3kg": 55, "per_kg_after_3_kg": 13},
            "Within State":       {"upto_3kg": 65, "per_kg_after_3_kg": 15},
            "Within Zone":        {"upto_3kg": 80, "per_kg_after_3_kg": 22},
            "Metros":             {"upto_3kg": 98, "per_kg_after_3_kg": 26},
            "Rest of india":      {"upto_3kg": 105,"per_kg_after_3_kg": 28},
            "Special destination":{"upto_3kg": 150,"per_kg_after_3_kg": 42},
            # Surcharges
            "fuel_surcharge_percentage": 0.10,
            "risk_on_value_percentage_safe_express": 0.001,
            "risk_surcharge_min": 50,
        },
    },

    "bluedart": {
        "volumetric_divisor": 4750,

        # Bluedart charges are route-multiplier based, not slab-by-destination.
        # Route multiplier matrix  (from_zone → to_zone → multiplier 1-4)
        "zone_multiplier": {
            "North": {"North": 1, "East": 1, "West": 2, "South": 3},
            "East":  {"North": 3, "East": 1, "West": 3, "South": 4},
            "West":  {"North": 2, "East": 3, "West": 1, "South": 2},
            "South": {"North": 3, "East": 4, "West": 2, "South": 1},
        },
        # Zone membership (state → zone)
        "state_zone_map": {
            "punjab": "North", "himachal pradesh": "North", "haryana": "North",
            "uttarakhand": "North", "uttar pradesh": "North", "rajasthan": "North",
            "chandigarh": "North",
            "bihar": "East", "orissa": "East", "west bengal": "East",
            "jharkhand": "East", "assam": "East",
            "maharashtra": "West", "madhya pradesh": "West", "gujarat": "West",
            "chhattisgarh": "West", "goa": "West", "diu and daman": "West",
            "karnataka": "South", "tamil nadu": "South", "kerala": "South",
            "andhra pradesh": "South", "telangana": "South", "pondicherry": "South",
        },
        # Flat rates used in the sample calculation
        "freight_min": 150,           # minimum freight INR
        "freight_percentage": 0.15,   # 15 % of declared value (whichever higher)
        "fuel_surcharge_percentage": 0.36,  # 36 %
        "currency_adjustment_factor_percentage": 0.20,   # CAF 20 %
        "non_document_charge": 50,
        "risk_charge": 100,
        "gst_percentage": 0.18,
    },
}


# ------------------------------------------------------------------
# 1E.  FEDEX FREIGHT RATES  (Fedex_freight.xlsx)
# ------------------------------------------------------------------
# Conditions:
#   shipment_type : "Envelope" | "Pak" | "Package"
#   zone          : "A" | "B" | "E" | "F" | "G" | "H" | "I" | "J" | "K" | "L"
#   weight_kg     : actual chargeable weight (volumetric vs actual, whichever >) 
#
# Lookup rule: find the row where weight_kg <= slab, read zone column.
# Fuel surcharge % is applied on top of base freight.
# Full weight table is too large to inline; keep the DB lookup for it.
# What IS hardcoded here: zone map + oversize/DG rules (already in STATIC_OTHER_CHARGES).

STATIC_FEDEX_ZONE_MAP = {
    # country (lowercase) → zone code
    "united arab emirates": "A",
    "pakistan": "B", "bangladesh": "B", "singapore": "B", "thailand": "B",
    "maldives": "B", "nepal": "B", "sri lanka": "B", "bhutan": "B",
    "egypt": "C", "iraq": "C", "jordan": "C", "lebanon": "C",
    "palestine authority": "C", "saudi arabia": "C",
    "china": "D", "hong kong sar, china": "D",
    "indonesia": "E", "korea, south": "E", "malaysia": "E",
    "taiwan, china": "E", "vietnam": "E",
    "belgium": "F", "denmark": "F", "france": "F", "germany": "F",
    "italy": "F", "netherlands": "F", "spain": "F", "switzerland": "F",
    "mexico": "G", "usa": "G", "united states": "G",
    "japan": "H", "mozambique": "H", "namibia": "H",
    "australia": "I", "austria": "I",
    # Zone J covers most of the remaining world
    "canada": "L",
}

STATIC_FEDEX_VOLUMETRIC_DIVISOR = 5000  # cm³ / 5000 = vol weight kg


# ------------------------------------------------------------------
# 1F.  UPS FREIGHT RATES  (UPS_Freight.xlsx)
# ------------------------------------------------------------------
# Conditions:
#   service_type : "LTR" | "Doc 0.5" | "NDC" (non-document cargo)
#   zone         : 01-10
#   weight_slab  : exact kg or range string (e.g. "21-44", "45-70")
#
# Same "full table in DB" approach; zone map hardcoded here.

STATIC_UPS_ZONE_MAP = {
    # country → import Express Saver zone (integer)
    "united arab emirates": 2, "bahrain": 3, "qatar": 3,
    "thailand": 1, "vietnam": 2, "australia": 2, "bangladesh": 3,
    "singapore": 2, "malaysia": 3,
    "united states": 5, "canada": 6,
    "united kingdom": 6, "germany": 6, "france": 6, "belgium": 6,
    "netherlands": 6, "switzerland": 7,
    "china": 2, "hong kong sar": 2, "japan": 3, "korea, south": 3,
}

STATIC_UPS_VOLUMETRIC_DIVISOR = 5000


# ─────────────────────────────────────────────────────────────────────────────
# 2.  SESSION-SCOPED OVERRIDE STORE
# ─────────────────────────────────────────────────────────────────────────────

_overrides: dict[str, dict] = {}
_lock = threading.Lock()


def override_charges(session_id: str, patches: dict) -> None:
    """
    Merge `patches` into the session override store for `session_id`.

    `patches` mirrors the structure of the static tables, e.g.:

        override_charges("sess-abc", {
            "clearance": {
                "FEDEX": {"LTL": {"advancement_charge": "900.00"}}
            },
            "bank": {"commission_charges": 600},
            "other": {"FEDEX": {"fuel_surcharge_percentage": 0.34}},
            "local": {"dtdc": {"safe_express": {"Metros": {"upto_3kg": 110}}}},
        })

    Only the keys present in `patches` are overridden; everything else
    falls back to the static defaults.
    """
    with _lock:
        existing = _overrides.get(session_id, {})
        _overrides[session_id] = _deep_merge(existing, patches)


def clear_overrides(session_id: str) -> None:
    """Remove all overrides for a session (call after quotation is finalised)."""
    with _lock:
        _overrides.pop(session_id, None)


def get_charges(session_id: str | None = None) -> dict:
    """
    Return the full charge set for `session_id`.

    Always starts from a deep-copy of the static tables so mutations in
    one session never bleed into another.
    """
    base = {
        "clearance": copy.deepcopy(STATIC_CLEARANCE_CHARGES),
        "other":     copy.deepcopy(STATIC_OTHER_CHARGES),
        "bank":      copy.deepcopy(STATIC_BANK_CHARGES),
        "local":     copy.deepcopy(STATIC_LOCAL_FREIGHT),
        "fedex_zone_map": STATIC_FEDEX_ZONE_MAP,       # read-only; no deepcopy needed
        "ups_zone_map":   STATIC_UPS_ZONE_MAP,
    }

    if session_id:
        with _lock:
            patches = _overrides.get(session_id, {})
        if patches:
            base = _deep_merge(base, patches)

    return base


# ─────────────────────────────────────────────────────────────────────────────
# 3.  INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _deep_merge(base: dict, patch: dict) -> dict:
    """
    Recursively merge `patch` into `base`.
    Scalar values in `patch` overwrite those in `base`.
    Dict values are merged recursively.
    """
    result = copy.deepcopy(base)
    for key, val in patch.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result
