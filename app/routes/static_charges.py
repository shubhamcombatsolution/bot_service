# """
# static_charges.py
# =================
# All charges stored as plain Python dicts — no DB required.
# The agent tool calls `override_charges(session_id, overrides)` to patch
# any value for a single session.  `get_charges(session_id)` returns the
# merged (static + override) charge set.

# Usage in calculation_engine_routes.py
# --------------------------------------
# from static_charges import get_charges, override_charges, clear_overrides

# # Agent tool calls this when the user provides a charge value:
# override_charges(session_id, {"FEDEX": {"clearance": {"LTL": {"advancement_charge": 900}}}})

# # Every builder function calls this instead of the DB:
# charges = get_charges(session_id)
# fedex_ltl = charges["FEDEX"]["clearance"]["LTL"]
# """

# import copy
# import threading

# # ─────────────────────────────────────────────────────────────────────────────
# # 1.  STATIC CHARGE TABLES  (sourced from Excel files & Erp_Configuration_RFQ)
# # ─────────────────────────────────────────────────────────────────────────────

# # ------------------------------------------------------------------
# # 1A.  CLEARANCE CHARGES  (Erp_Configuration_RFQ → Customs Clearance)
# # ------------------------------------------------------------------
# # Conditions:
# #   carrier  : "FEDEX" | "UPS" | "FF"  (freight-forwarder)
# #   shipment : "LTL"  (courier_lt_1_lakh) | "GTL" (cargo_gt_1_lakh)
# #   For FF only GTL-equivalent rows exist (no courier mode)
# #
# # Fields that are per-kg also carry a _per_kg sibling.
# # duties_tax_percentage : 2 % on the customs-cleared invoice value.

# STATIC_CLEARANCE_CHARGES = {
#     # ── FEDEX ────────────────────────────────────────────────────────────
#     "FEDEX": {
#         # Courier mode  (invoice < 1 lakh INR)
#         "LTL": {
#             "duties_tax_percentage": "0.02",           # 2 %
#             "advancement_charge": "800.00",            # min INR 800 or 2 % whichever > (use duties_tax for %)
#             "courier_handling_charges": "356.00",
#             "courier_handling_charges_per_kg": "10.79",
#         },
#         # Cargo mode  (invoice ≥ 1 lakh INR)
#         "GTL": {
#             "duties_tax_percentage": "0.02",
#             "advancement_charge": "800.00",
#             "formal_boe_charge": "1800.00",
#             "TSP_general_charge": "223.00",
#             "TSP_general_charge_prise_per_kg": "9.61",
#             "TSP_special_cargo_charge": "445.00",
#             "TSP_special_cargo_charge_prise_per_kg": "19.22",
#             "demurrage_charges_General": "598.00",
#             "demurrage_charges_General_prise_per_kg": "2.95",
#             "demurrage_special_cargo_charges": "1113.00",
#             "demurrage_special_cargo_charges_prise_per_kg": "10.97",
#             "documentation_charge_per_AWB": "200.00",
#         },
#     },

#     # ── UPS ──────────────────────────────────────────────────────────────
#     "UPS": {
#         # Courier mode
#         "LTL": {
#             "duties_tax_percentage": "0.02",
#             "advancement_charge": "788.00",            # UPS uses 788, not 800
#             "courier_handling_charges": "356.00",
#             "courier_handling_charges_per_kg": "10.79",
#         },
#         # Cargo mode
#         "GTL": {
#             "duties_tax_percentage": "0.02",
#             "advancement_charge": "800.00",
#             "formal_boe_charge": "1800.00",
#             "TSP_general_charge": "223.00",
#             "TSP_general_charge_prise_per_kg": "9.61",
#             "TSP_special_cargo_charge": "445.00",
#             "TSP_special_cargo_charge_prise_per_kg": "19.22",
#             "demurrage_charges_General": "598.00",
#             "demurrage_charges_General_prise_per_kg": "2.95",
#             "demurrage_special_cargo_charges": "1113.00",
#             "demurrage_special_cargo_charges_prise_per_kg": "10.97",
#             "documentation_charge_per_AWB": "200.00",
#         },
#     },

#     # ── FREIGHT FORWARDER (FF) ───────────────────────────────────────────
#     # Conditions: always cargo mode; transportation & DO Fee are extra.
#     "FF": {
#         "GTL": {
#             "duties_tax_percentage": "0.02",
#             "advancement_charge": "800.00",
#             "formal_boe_charge": "2600.00",            # FF formal BOE is higher
#             "TSP_general_charge": "223.00",
#             "TSP_general_charge_prise_per_kg": "9.61",
#             "TSP_special_cargo_charge": "445.00",
#             "TSP_special_cargo_charge_prise_per_kg": "19.22",
#             "demurrage_charges_General": "598.00",
#             "demurrage_charges_General_prise_per_kg": "2.95",
#             "demurrage_special_cargo_charges": "1113.00",
#             "demurrage_special_cargo_charges_prise_per_kg": "10.97",
#             "documentation_charge_per_AWB": "200.00",
#             "transportation_charges": "2000.00",
#             "DO_fee": "3575.00",
#         },
#     },
# }


# # ------------------------------------------------------------------
# # 1B.  OTHER / FREIGHT SURCHARGES
# #       (Fedex_freight.xlsx + UPS_Freight.xlsx)
# # ------------------------------------------------------------------
# # Conditions:
# #   carrier            : "FEDEX" | "UPS" | "COMMON"
# #   charge_category    : "fuel_surcharge" | "dangerous_goods" | "oversize" | "surge_fee"
# #
# # fuel_surcharge_percentage : multiplied against base freight.
# # oversize_threshold_cm     : package longest-side > this → oversize charge applies.
# # surge_fee rows give per-kg surcharge by destination group.

# STATIC_OTHER_CHARGES = {
#     "FEDEX": {
#         # Fuel surcharge — check https://www.fedex.com/en-in/shipping/surcharges.html for current %.
#         # As of March 2025 the published rate is 33.5 %.
#         "fuel_surcharge_percentage": 0.335,

#         # Oversize: longest dimension > 120 cm → flat INR 20,500
#         "oversize_threshold_cm": 120,
#         "oversize_charge_inr": 20500,
#     },

#     "UPS": {
#         # Fuel surcharge — published at 32.5 %
#         "fuel_surcharge_percentage": 0.325,

#         # Oversize: longest dimension > 120 cm → flat INR 8,723
#         "oversize_threshold_cm": 120,
#         "oversize_charge_inr": 8723,

#         # Surge fees (per-shipment, India origin)
#         # Conditions: destination_group matches one of the keys below.
#         "surge_fees": {
#             "U.S":          38,    # India → U.S.
#             "Europe":       43,    # India → Europe
#             "Israel":       55,
#             "China":        10,    # China Mainland, HK SAR, Macau SAR
#             "Asia Pacific": 10,
#         },
#     },

#     "COMMON": {
#         # Accessible Dangerous Goods — applies to BOTH FedEx & UPS
#         # Conditions: supplier.accessible_dangerous_goods == True
#         "accessible_dangerous_goods_charge_min": 2750,   # INR minimum
#         "accessible_dangerous_goods_charge_per_kg": 45,
#     },
# }


# # ------------------------------------------------------------------
# # 1C.  BANK CHARGES  (Erp_Configuration_RFQ → Forex Bank Charges)
# # ------------------------------------------------------------------
# # Conditions: always applied on global (forex) shipments.
# # DBS_percentage    : applied on the foreign-currency invoice total.
# # commission_charges: flat INR per transaction.
# # cable_charges     : flat INR per wire transfer.

# STATIC_BANK_CHARGES = {
#     "DBS_percentage": 0.0025,    # 0.25 % bank commission
#     "commission_charges": 500.0,
#     "cable_charges": 500.0,
# }


# # ------------------------------------------------------------------
# # 1D.  LOCAL FREIGHT CHARGES  (Local_freight.xlsx)
# # ------------------------------------------------------------------
# # Conditions:
# #   carrier           : "dtdc" | "bluedart"
# #   service_type      : "priority" | "safe_express" (DTDC only)
# #   delivery_category : "Within City" | "Within State" | "Within Zone"
# #                       | "Metros" | "Rest of india" | "Special destination"
# #
# # Weight slab logic (DTDC):
# #   upto_half_kg      : base rate up to 500 g
# #   additional_per_half_kg : per additional 500 g block
# #   per_kg_after_10_kg: per kg once total > 10 kg
# # Volumetric divisor  : 4750

# STATIC_LOCAL_FREIGHT = {
#     "dtdc": {
#         "volumetric_divisor": 4750,

#         # DTDC Priority  — weight slabs in INR
#         "priority": {
#             "Within City":        {"upto_half_kg": 25, "additional_per_half_kg": 15, "per_kg_after_10_kg": 26},
#             "Within State":       {"upto_half_kg": 34, "additional_per_half_kg": 21, "per_kg_after_10_kg": 33},
#             "Within Zone":        {"upto_half_kg": 38, "additional_per_half_kg": 27, "per_kg_after_10_kg": 45},
#             "Metros":             {"upto_half_kg": 50, "additional_per_half_kg": 45, "per_kg_after_10_kg": 83},
#             "Rest of india":      {"upto_half_kg": 55, "additional_per_half_kg": 50, "per_kg_after_10_kg": 90},
#             "Special destination":{"upto_half_kg": 87, "additional_per_half_kg": 77, "per_kg_after_10_kg": 140},
#             # Surcharges (apply on top of base freight)
#             "fuel_surcharge_percentage": 0.10,          # 10 %
#             "risk_on_value_percentage_priority": 0.001, # 0.1 % of invoice, min 50
#             "risk_surcharge_min": 50,
#         },

#         # DTDC Safe Express  — weight slabs in INR
#         "safe_express": {
#             "Within City":        {"upto_3kg": 55, "per_kg_after_3_kg": 13},
#             "Within State":       {"upto_3kg": 65, "per_kg_after_3_kg": 15},
#             "Within Zone":        {"upto_3kg": 80, "per_kg_after_3_kg": 22},
#             "Metros":             {"upto_3kg": 98, "per_kg_after_3_kg": 26},
#             "Rest of india":      {"upto_3kg": 105,"per_kg_after_3_kg": 28},
#             "Special destination":{"upto_3kg": 150,"per_kg_after_3_kg": 42},
#             # Surcharges
#             "fuel_surcharge_percentage": 0.10,
#             "risk_on_value_percentage_safe_express": 0.001,
#             "risk_surcharge_min": 50,
#         },
#     },

#     "bluedart": {
#         "volumetric_divisor": 4750,

#         # Bluedart charges are route-multiplier based, not slab-by-destination.
#         # Route multiplier matrix  (from_zone → to_zone → multiplier 1-4)
#         "zone_multiplier": {
#             "North": {"North": 1, "East": 1, "West": 2, "South": 3},
#             "East":  {"North": 3, "East": 1, "West": 3, "South": 4},
#             "West":  {"North": 2, "East": 3, "West": 1, "South": 2},
#             "South": {"North": 3, "East": 4, "West": 2, "South": 1},
#         },
#         # Zone membership (state → zone)
#         "state_zone_map": {
#             "punjab": "North", "himachal pradesh": "North", "haryana": "North",
#             "uttarakhand": "North", "uttar pradesh": "North", "rajasthan": "North",
#             "chandigarh": "North",
#             "bihar": "East", "orissa": "East", "west bengal": "East",
#             "jharkhand": "East", "assam": "East",
#             "maharashtra": "West", "madhya pradesh": "West", "gujarat": "West",
#             "chhattisgarh": "West", "goa": "West", "diu and daman": "West",
#             "karnataka": "South", "tamil nadu": "South", "kerala": "South",
#             "andhra pradesh": "South", "telangana": "South", "pondicherry": "South",
#         },
#         # Flat rates used in the sample calculation
#         "freight_min": 150,           # minimum freight INR
#         "freight_percentage": 0.15,   # 15 % of declared value (whichever higher)
#         "fuel_surcharge_percentage": 0.36,  # 36 %
#         "currency_adjustment_factor_percentage": 0.20,   # CAF 20 %
#         "non_document_charge": 50,
#         "risk_charge": 100,
#         "gst_percentage": 0.18,
#     },
# }


# # ------------------------------------------------------------------
# # 1E.  FEDEX FREIGHT RATES  (Fedex_freight.xlsx)
# # ------------------------------------------------------------------
# # Conditions:
# #   shipment_type : "Envelope" | "Pak" | "Package"
# #   zone          : "A" | "B" | "E" | "F" | "G" | "H" | "I" | "J" | "K" | "L"
# #   weight_kg     : actual chargeable weight (volumetric vs actual, whichever >) 
# #
# # Lookup rule: find the row where weight_kg <= slab, read zone column.
# # Fuel surcharge % is applied on top of base freight.
# # Full weight table is too large to inline; keep the DB lookup for it.
# # What IS hardcoded here: zone map + oversize/DG rules (already in STATIC_OTHER_CHARGES).

# STATIC_FEDEX_ZONE_MAP = {
#     # country (lowercase) → zone code
#     "united arab emirates": "A",
#     "pakistan": "B", "bangladesh": "B", "singapore": "B", "thailand": "B",
#     "maldives": "B", "nepal": "B", "sri lanka": "B", "bhutan": "B",
#     "egypt": "C", "iraq": "C", "jordan": "C", "lebanon": "C",
#     "palestine authority": "C", "saudi arabia": "C",
#     "china": "D", "hong kong sar, china": "D",
#     "indonesia": "E", "korea, south": "E", "malaysia": "E",
#     "taiwan, china": "E", "vietnam": "E",
#     "belgium": "F", "denmark": "F", "france": "F", "germany": "F",
#     "italy": "F", "netherlands": "F", "spain": "F", "switzerland": "F",
#     "mexico": "G", "usa": "G", "united states": "G",
#     "japan": "H", "mozambique": "H", "namibia": "H",
#     "australia": "I", "austria": "I",
#     # Zone J covers most of the remaining world
#     "canada": "L",
# }

# STATIC_FEDEX_VOLUMETRIC_DIVISOR = 5000  # cm³ / 5000 = vol weight kg


# # ------------------------------------------------------------------
# # 1F.  UPS FREIGHT RATES  (UPS_Freight.xlsx)
# # ------------------------------------------------------------------
# # Conditions:
# #   service_type : "LTR" | "Doc 0.5" | "NDC" (non-document cargo)
# #   zone         : 01-10
# #   weight_slab  : exact kg or range string (e.g. "21-44", "45-70")
# #
# # Same "full table in DB" approach; zone map hardcoded here.

# STATIC_UPS_ZONE_MAP = {
#     # country → import Express Saver zone (integer)
#     "united arab emirates": 2, "bahrain": 3, "qatar": 3,
#     "thailand": 1, "vietnam": 2, "australia": 2, "bangladesh": 3,
#     "singapore": 2, "malaysia": 3,
#     "united states": 5, "canada": 6,
#     "united kingdom": 6, "germany": 6, "france": 6, "belgium": 6,
#     "netherlands": 6, "switzerland": 7,
#     "china": 2, "hong kong sar": 2, "japan": 3, "korea, south": 3,
# }

# STATIC_UPS_VOLUMETRIC_DIVISOR = 5000


# # ─────────────────────────────────────────────────────────────────────────────
# # 2.  SESSION-SCOPED OVERRIDE STORE
# # ─────────────────────────────────────────────────────────────────────────────

# _overrides: dict[str, dict] = {}
# _lock = threading.Lock()


# def override_charges(session_id: str, patches: dict) -> None:
#     """
#     Merge `patches` into the session override store for `session_id`.

#     `patches` mirrors the structure of the static tables, e.g.:

#         override_charges("sess-abc", {
#             "clearance": {
#                 "FEDEX": {"LTL": {"advancement_charge": "900.00"}}
#             },
#             "bank": {"commission_charges": 600},
#             "other": {"FEDEX": {"fuel_surcharge_percentage": 0.34}},
#             "local": {"dtdc": {"safe_express": {"Metros": {"upto_3kg": 110}}}},
#         })

#     Only the keys present in `patches` are overridden; everything else
#     falls back to the static defaults.
#     """
#     with _lock:
#         existing = _overrides.get(session_id, {})
#         _overrides[session_id] = _deep_merge(existing, patches)


# def clear_overrides(session_id: str) -> None:
#     """Remove all overrides for a session (call after quotation is finalised)."""
#     with _lock:
#         _overrides.pop(session_id, None)


# def get_charges(session_id: str | None = None) -> dict:
#     """
#     Return the full charge set for `session_id`.

#     Always starts from a deep-copy of the static tables so mutations in
#     one session never bleed into another.
#     """
#     base = {
#         "clearance": copy.deepcopy(STATIC_CLEARANCE_CHARGES),
#         "other":     copy.deepcopy(STATIC_OTHER_CHARGES),
#         "bank":      copy.deepcopy(STATIC_BANK_CHARGES),
#         "local":     copy.deepcopy(STATIC_LOCAL_FREIGHT),
#         "fedex_zone_map": STATIC_FEDEX_ZONE_MAP,       # read-only; no deepcopy needed
#         "ups_zone_map":   STATIC_UPS_ZONE_MAP,
#     }

#     if session_id:
#         with _lock:
#             patches = _overrides.get(session_id, {})
#         if patches:
#             base = _deep_merge(base, patches)

#     return base


# # ─────────────────────────────────────────────────────────────────────────────
# # 3.  INTERNAL HELPERS
# # ─────────────────────────────────────────────────────────────────────────────

# def _deep_merge(base: dict, patch: dict) -> dict:
#     """
#     Recursively merge `patch` into `base`.
#     Scalar values in `patch` overwrite those in `base`.
#     Dict values are merged recursively.
#     """
#     result = copy.deepcopy(base)
#     for key, val in patch.items():
#         if key in result and isinstance(result[key], dict) and isinstance(val, dict):
#             result[key] = _deep_merge(result[key], val)
#         else:
#             result[key] = copy.deepcopy(val)
#     return result
































"""
static_charges.py
=================
All charges stored as plain Python dicts — no DB required.
The agent tool calls `override_charges(session_id, overrides)` to patch
any value for a single session.  `get_charges(session_id)` returns the
merged (static + override) charge set.

Now includes full FedEx & UPS freight rate tables (from PDF reference guide,
March 2025). The route/calculation files query get_fedex_freight_rate() and
get_ups_freight_rate() instead of the database for rate lookups.

Usage in calculation_engine_routes.py
--------------------------------------
from static_charges import get_charges, override_charges, clear_overrides
from static_charges import get_fedex_freight_rate, get_ups_freight_rate

# Agent tool calls this when the user provides a charge value:
override_charges(session_id, {"FEDEX": {"clearance": {"LTL": {"advancement_charge": 900}}}})

# Every builder function calls this instead of the DB:
charges = get_charges(session_id)
fedex_ltl = charges["clearance"]["FEDEX"]["LTL"]

# Rate table lookups (replaces DB queries):
rate = get_fedex_freight_rate(package_type="Package", weight_kg=6.5, zone="G")
rate = get_ups_freight_rate(package_type="NDC", weight_kg=6.5, zone_code="05")
"""

import copy
import threading
from decimal import Decimal

# ─────────────────────────────────────────────────────────────────────────────
# 1.  STATIC CHARGE TABLES  (sourced from PDF: Freight Charges Reference Guide)
# ─────────────────────────────────────────────────────────────────────────────

# ------------------------------------------------------------------
# 1A.  CLEARANCE CHARGES  (PDF Section 11)
# ------------------------------------------------------------------
# carrier  : "FEDEX" | "UPS" | "FF"  (freight-forwarder)
# shipment : "LTL" (courier < 1 lakh) | "GTL" (cargo >= 1 lakh)

STATIC_CLEARANCE_CHARGES = {
    # ── FEDEX ────────────────────────────────────────────────────────────
    "FEDEX": {
        # Courier mode  (invoice < 1 lakh INR) — PDF Section 11a
        "LTL": {
            "duties_tax_percentage":              "0.02",    # 2%
            "advancement_charge":                 "800.00",  # min ₹800 or 2% duties, whichever >
            "courier_handling_charges":           "356.00",
            "courier_handling_charges_per_kg":    "10.79",
        },
        # Cargo mode  (invoice ≥ 1 lakh INR) — PDF Section 11b
        "GTL": {
            "duties_tax_percentage":                         "0.02",
            "advancement_charge":                            "800.00",
            "formal_boe_charge":                             "1800.00",
            "TSP_general_charge":                            "223.00",
            "TSP_general_charge_prise_per_kg":               "9.61",
            "TSP_special_cargo_charge":                      "445.00",
            "TSP_special_cargo_charge_prise_per_kg":         "19.22",
            "demurrage_charges_General":                     "598.00",
            "demurrage_charges_General_prise_per_kg":        "2.95",
            "demurrage_special_cargo_charges":               "1113.00",
            "demurrage_special_cargo_charges_prise_per_kg":  "10.97",
            "documentation_charge_per_AWB":                  "200.00",
        },
    },

    # ── UPS ──────────────────────────────────────────────────────────────
    "UPS": {
        # Courier mode — PDF Section 11c
        "LTL": {
            "duties_tax_percentage":              "0.02",
            "advancement_charge":                 "788.00",  # UPS uses 788, not 800
            "courier_handling_charges":           "356.00",
            "courier_handling_charges_per_kg":    "10.79",
        },
        # Cargo mode — PDF Section 11b (same as FedEx cargo)
        "GTL": {
            "duties_tax_percentage":                         "0.02",
            "advancement_charge":                            "800.00",
            "formal_boe_charge":                             "1800.00",
            "TSP_general_charge":                            "223.00",
            "TSP_general_charge_prise_per_kg":               "9.61",
            "TSP_special_cargo_charge":                      "445.00",
            "TSP_special_cargo_charge_prise_per_kg":         "19.22",
            "demurrage_charges_General":                     "598.00",
            "demurrage_charges_General_prise_per_kg":        "2.95",
            "demurrage_special_cargo_charges":               "1113.00",
            "demurrage_special_cargo_charges_prise_per_kg":  "10.97",
            "documentation_charge_per_AWB":                  "200.00",
        },
    },

    # ── FREIGHT FORWARDER (FF) — PDF Section 11d ─────────────────────────
    "FF": {
        "GTL": {
            "duties_tax_percentage":                         "0.02",
            "advancement_charge":                            "800.00",
            "formal_boe_charge":                             "2600.00",  # FF BOE is higher
            "TSP_general_charge":                            "223.00",
            "TSP_general_charge_prise_per_kg":               "9.61",
            "TSP_special_cargo_charge":                      "445.00",
            "TSP_special_cargo_charge_prise_per_kg":         "19.22",
            "demurrage_charges_General":                     "598.00",
            "demurrage_charges_General_prise_per_kg":        "2.95",
            "demurrage_special_cargo_charges":               "1113.00",
            "demurrage_special_cargo_charges_prise_per_kg":  "10.97",
            "documentation_charge_per_AWB":                  "200.00",
            "transportation_charges":                        "2000.00",
            "DO_fee":                                        "3575.00",
        },
    },
}


# ------------------------------------------------------------------
# 1B.  OTHER / FREIGHT SURCHARGES  (PDF Sections 3, 7)
# ------------------------------------------------------------------

STATIC_OTHER_CHARGES = {
    "FEDEX": {
        # PDF Section 4: Fuel surcharge — check fedex.com; rate as of March 2025 = 33.5%
        "fuel_surcharge_percentage": 0.335,

        # PDF Section 3: Oversize — longest side > 120 cm → ₹20,500
        "oversize_threshold_cm":   120,
        "oversize_charge_inr":     20500,
    },

    "UPS": {
        # PDF Section 8: Fuel surcharge — 32.5%
        "fuel_surcharge_percentage": 0.325,

        # PDF Section 7b: Oversize — longest side > 120 cm → ₹8,723
        "oversize_threshold_cm":   120,
        "oversize_charge_inr":     8723,

        # PDF Section 7a: Surge fees per shipment from India
        "surge_fees": {
            "U.S.A.":       38,   # India → U.S.A.
            "U.S":          38,   # alias
            "Europe":       43,
            "Israel":       55,
            "China":        10,   # China Mainland, HK SAR, Macau SAR
            "Asia Pacific": 10,
        },
    },

    "COMMON": {
        # PDF Section 3: Accessible Dangerous Goods — both FedEx & UPS
        "accessible_dangerous_goods_charge_min":    2750,   # ₹ minimum
        "accessible_dangerous_goods_charge_per_kg":   45,
    },
}


# ------------------------------------------------------------------
# 1C.  BANK CHARGES
# ------------------------------------------------------------------

STATIC_BANK_CHARGES = {
    "DBS_percentage":    0.0025,   # 0.25% bank commission
    "commission_charges": 500.0,
    "cable_charges":      500.0,
}


# ------------------------------------------------------------------
# 1D.  LOCAL FREIGHT CHARGES  (PDF Sections 9, 10)
# ------------------------------------------------------------------

STATIC_LOCAL_FREIGHT = {
    "dtdc": {
        "volumetric_divisor": 4750,  # PDF Section 9: L×B×H ÷ 4750

        # PDF Section 9a: DTDC Priority rates (INR)
        # upto_250g column exists in PDF but is blank/dash — not billable separately
        "priority": {
            "Within City":         {"upto_half_kg": 25,  "additional_per_half_kg": 15, "per_kg_after_10_kg": 26},
            "Within State":        {"upto_half_kg": 34,  "additional_per_half_kg": 21, "per_kg_after_10_kg": 33},
            "Within Zone":         {"upto_half_kg": 38,  "additional_per_half_kg": 27, "per_kg_after_10_kg": 45},
            "Metros":              {"upto_half_kg": 50,  "additional_per_half_kg": 45, "per_kg_after_10_kg": 83},
            "Rest of india":       {"upto_half_kg": 55,  "additional_per_half_kg": 50, "per_kg_after_10_kg": 90},
            "Special destination": {"upto_half_kg": 87,  "additional_per_half_kg": 77, "per_kg_after_10_kg": 140},
            # PDF Section 9: Surcharges
            "fuel_surcharge_percentage":            0.10,   # 10%
            "risk_on_value_percentage_priority":    0.001,  # 0.1% of invoice value
            "risk_surcharge_min":                   50,
        },

        # PDF Section 9b: DTDC Safe Express (Ground) rates (INR)
        "safe_express": {
            "Within City":         {"upto_3kg": 55,  "per_kg_after_3_kg": 13},
            "Within State":        {"upto_3kg": 65,  "per_kg_after_3_kg": 15},
            "Within Zone":         {"upto_3kg": 80,  "per_kg_after_3_kg": 22},
            "Metros":              {"upto_3kg": 98,  "per_kg_after_3_kg": 26},
            "Rest of india":       {"upto_3kg": 105, "per_kg_after_3_kg": 28},
            "Special destination": {"upto_3kg": 150, "per_kg_after_3_kg": 42},
            # PDF Section 9: Surcharges
            "fuel_surcharge_percentage":              0.10,
            "risk_on_value_percentage_safe_express":  0.001,
            "risk_surcharge_min":                     50,
        },
    },

    "bluedart": {
        "volumetric_divisor": 4750,

        # PDF Section 10b: Zone multiplier matrix
        "zone_multiplier": {
            "North": {"North": 1, "East": 1, "West": 2, "South": 3},
            "East":  {"North": 3, "East": 1, "West": 3, "South": 4},
            "West":  {"North": 2, "East": 3, "West": 1, "South": 2},
            "South": {"North": 3, "East": 4, "West": 2, "South": 1},
        },

        # PDF Section 10a: State → zone
        "state_zone_map": {
            "punjab":            "North", "himachal pradesh": "North",
            "haryana":           "North", "uttarakhand":      "North",
            "uttar pradesh":     "North", "rajasthan":        "North",
            "chandigarh":        "North",
            "bihar":             "East",  "orissa":           "East",
            "west bengal":       "East",  "jharkhand":        "East",
            "assam":             "East",
            "maharashtra":       "West",  "madhya pradesh":   "West",
            "gujarat":           "West",  "chhattisgarh":     "West",
            "goa":               "West",  "diu and daman":    "West",
            "karnataka":         "South", "tamil nadu":       "South",
            "kerala":            "South", "andhra pradesh":   "South",
            "telangana":         "South", "pondicherry":      "South",
        },

        # PDF Section 10c: Sample rate structure
        "freight_min":                         150,
        "freight_percentage":                  0.15,   # 15% of declared value
        "fuel_surcharge_percentage":           0.36,   # 36%
        "currency_adjustment_factor_percentage": 0.20, # CAF 20%
        "non_document_charge":                 50,
        "risk_charge":                         100,
        "gst_percentage":                      0.18,
    },
}


# ------------------------------------------------------------------
# 1E.  FEDEX ZONE MAP  (PDF Section 2 — complete country list)
# ------------------------------------------------------------------
# country name (lowercase) → zone code (single letter A–L)
# Zones C and D exist in the PDF zone reference but have NO rate columns
# in the rate table (they are handled differently / not imported to India).
# Origin: India | Service: International Priority Import

STATIC_FEDEX_ZONE_MAP = {
    # Zone A
    "united arab emirates": "A",

    # Zone B
    "bangladesh": "B", "bhutan": "B", "maldives": "B", "nepal": "B",
    "pakistan": "B", "philippines": "B", "singapore": "B",
    "sri lanka": "B", "thailand": "B",

    # Zone C  (no rate column — flagged in lookup)
    "afghanistan": "C", "egypt": "C", "iraq": "C", "jordan": "C",
    "lebanon": "C", "palestine authority": "C", "saudi arabia": "C",
    "syria": "C",

    # Zone D  (no rate column — flagged in lookup)
    "china": "D", "hong kong sar, china": "D", "hong kong sar": "D",

    # Zone E
    "brunei": "E", "cambodia": "E", "east timor": "E",
    "indonesia": "E", "korea, south": "E", "laos": "E",
    "macao sar, china": "E", "macao sar": "E",
    "malaysia": "E", "mongolia": "E", "montenegro": "E",
    "taiwan, china": "E", "taiwan": "E", "vietnam": "E",
    "vanuatu": "E",

    # Zone F
    "belgium": "F", "denmark": "F", "france": "F", "germany": "F",
    "great britain": "F", "italy": "F", "liechtenstein": "F",
    "luxembourg": "F", "netherlands": "F", "samoa, west": "F",
    "san marino": "F", "spain": "F", "switzerland": "F",
    "vatican city": "F",

    # Zone G
    "mexico": "G", "usa": "G", "united states": "G",
    "united states of america": "G",

    # Zone H
    "japan": "H", "mozambique": "H", "namibia": "H",

    # Zone I
    "australia": "I", "austria": "I", "bulgaria": "I", "cyprus": "I",
    "czech republic": "I", "finland": "I", "gibraltar": "I",
    "greece": "I", "hungary": "I", "iceland": "I", "ireland": "I",
    "israel": "I", "malta": "I", "monaco": "I", "new zealand": "I",
    "norway": "I", "papua - new guinea": "I", "papua new guinea": "I",
    "poland": "I", "portugal": "I", "puerto rico": "I", "romania": "I",
    "sweden": "I", "turkey": "I",

    # Zone J  (most remaining world destinations)
    "albania": "J", "algeria": "J", "angola": "J", "anguilla": "J",
    "antigua & barbuda": "J", "argentina": "J", "armenia": "J",
    "aruba": "J", "azerbaijan": "J", "bahamas": "J",
    "barbados": "J", "belarus": "J", "belize": "J", "benin": "J",
    "bermuda": "J", "bolivia": "J",
    "bonaire, saba, st. eustatius": "J", "bosnia-herzegovina": "J",
    "botswana": "J", "brazil": "J", "burkina faso": "J",
    "burundi": "J", "canada": "J",   # NOTE: overridden below to L
    "cape verde": "J", "cayman islands": "J", "chad": "J",
    "chile": "J", "colombia": "J", "congo": "J",
    "congo, dem. rep. of": "J", "costa rica": "J", "croatia": "J",
    "curacao": "J", "djibouti": "J", "dominica": "J",
    "dominican republic": "J", "ecuador": "J", "el salvador": "J",
    "eritrea": "J", "estonia": "J", "ethiopia": "J", "fiji": "J",
    "french guiana": "J", "french polynesia": "J", "gabon": "J",
    "gambia": "J", "georgia": "J", "ghana": "J",
    "grenada": "J", "guadeloupe": "J", "guam": "J",
    "guatemala": "J", "guinea": "J", "guyana": "J", "haiti": "J",
    "honduras": "J", "ivory coast": "J", "jamaica": "J",
    "kazakhstan": "J", "kenya": "J", "kyrgyzstan": "J",
    "latvia": "J", "lesotho": "J", "liberia": "J", "libya": "J",
    "lithuania": "J", "madagascar": "J", "malawi": "J",
    "mali": "J", "martinique": "J", "mauritania": "J",
    "mauritius": "J", "moldova": "J", "montserrat": "J",
    "morocco": "J", "new caledonia": "J", "nicaragua": "J",
    "niger": "J", "nigeria": "J", "north macedonia": "J",
    "panama": "J", "paraguay": "J", "peru": "J",
    "reunion island": "J", "russia": "J", "rwanda": "J",
    "senegal": "J", "serbia": "J", "seychelles": "J",
    "slovak republic": "J", "slovenia": "J", "south africa": "J",
    "st. kitts & nevis": "J", "st. lucia": "J",
    "st. maarten (nl)": "J", "st. martin (fr)": "J",
    "st. vincent": "J", "suriname": "J", "swaziland": "J",
    "tanzania": "J", "togo": "J", "trinidad & tobago": "J",
    "tunisia": "J", "turks & caicos islands": "J",
    "uganda": "J", "ukraine": "J", "uruguay": "J",
    "uzbekistan": "J", "venezuela": "J",
    "virgin islands (gb)": "J", "virgin islands (usa)": "J",
    "wallis & futuna": "J", "zambia": "J", "zimbabwe": "J",

    # Zone K
    "bahrain": "K", "kuwait": "K", "oman": "K", "qatar": "K",

    # Zone L  (overrides J entry above)
    "canada": "L",
}

STATIC_FEDEX_VOLUMETRIC_DIVISOR = 5000   # cm³ ÷ 5000 = vol weight kg


# ------------------------------------------------------------------
# 1F.  FEDEX FREIGHT RATE TABLE  (PDF Sections 1a–1d)
# ------------------------------------------------------------------
# Structure:
#   STATIC_FEDEX_RATES[package_type][weight_kg] = {zone: rate_inr, ...}
#
# package_type : "Envelope" | "Pak" | "Package"
# weight_kg    : float (exact slab values from PDF)
# zone         : "A" | "B" | "E" | "F" | "G" | "H" | "I" | "J" | "K" | "L"
#
# Lookup rule: find exact weight_kg slab in sorted list, pick zone column.
# Note: Zones C & D are not in the rate table (different service path).

STATIC_FEDEX_RATES = {

    # ── 1a. Envelope (flat rate, no weight column) ──────────────────────
    "Envelope": {
        # single flat rate regardless of weight
        0.5: {
            "A":  815.8,  "B":  787.9,  "E":  806.7,  "F": 1530.7,
            "G": 1554.9,  "H": 1136.9,  "I": 1596.9,  "J": 1834.9,
            "K": 1125.5,  "L":  983.9,
        },
    },

    # ── 1b. Pak (0.5 – 2.5 kg) ──────────────────────────────────────────
    "Pak": {
        0.5: {"A":  956.3, "B":  853.9, "E":  948.0, "F": 1595.8, "G": 1691.7, "H": 1137.1, "I": 1596.7, "J": 2214.1, "K": 1403.7, "L": 1220.5},
        1.0: {"A": 1050.7, "B": 1024.0, "E": 1117.8, "F": 1856.6, "G": 1952.5, "H": 1232.2, "I": 1857.3, "J": 2613.8, "K": 1551.0, "L": 1491.7},
        1.5: {"A": 1146.7, "B": 1192.3, "E": 1287.5, "F": 2162.0, "G": 2281.7, "H": 1361.9, "I": 2163.8, "J": 3021.5, "K": 1698.3, "L": 1761.8},
        2.0: {"A": 1240.8, "B": 1360.3, "E": 1457.7, "F": 2467.4, "G": 2609.4, "H": 1488.5, "I": 2465.2, "J": 3427.6, "K": 1845.2, "L": 2032.0},
        2.5: {"A": 1336.0, "B": 1528.7, "E": 1626.8, "F": 2771.8, "G": 2935.1, "H": 1618.0, "I": 2771.2, "J": 3833.9, "K": 1992.7, "L": 2302.2},
    },

    # ── 1c & 1d. Package (0.5 – 70.5 kg) ───────────────────────────────
    "Package": {
        # 0.5 – 20.5 kg (Section 1c)
        0.5:  {"A": 1130.2, "B": 1144.1, "E": 1131.7, "F": 1709.9, "G": 1807.8, "H": 1319.8, "I": 1711.4, "J": 2481.1, "K": 1905.1, "L": 1499.6},
        1.0:  {"A": 1132.0, "B": 1277.1, "E": 1251.1, "F": 1975.5, "G": 2090.7, "H": 1344.8, "I": 1953.4, "J": 2781.8, "K": 1906.3, "L": 1797.8},
        1.5:  {"A": 1306.4, "B": 1473.5, "E": 1450.0, "F": 2241.2, "G": 2372.0, "H": 1549.1, "I": 2235.7, "J": 3213.5, "K": 2199.9, "L": 2039.0},
        2.0:  {"A": 1480.8, "B": 1669.9, "E": 1648.9, "F": 2506.8, "G": 2653.3, "H": 1753.3, "I": 2518.0, "J": 3645.2, "K": 2493.4, "L": 2280.1},
        2.5:  {"A": 1655.1, "B": 1866.4, "E": 1847.8, "F": 2772.4, "G": 2934.6, "H": 1957.5, "I": 2800.3, "J": 4076.9, "K": 2786.9, "L": 2521.3},
        3.0:  {"A": 1656.8, "B": 2053.6, "E": 2034.2, "F": 2998.5, "G": 3200.5, "H": 1958.0, "I": 2935.6, "J": 4450.9, "K": 2790.2, "L": 2879.4},
        3.5:  {"A": 1753.3, "B": 2180.9, "E": 2176.1, "F": 3224.7, "G": 3467.7, "H": 2127.0, "I": 3197.8, "J": 4826.6, "K": 2952.9, "L": 3120.6},
        4.0:  {"A": 1849.7, "B": 2308.1, "E": 2318.1, "F": 3450.8, "G": 3734.8, "H": 2296.0, "I": 3460.0, "J": 5202.2, "K": 3115.5, "L": 3361.8},
        4.5:  {"A": 1946.1, "B": 2435.4, "E": 2460.0, "F": 3677.0, "G": 4002.0, "H": 2465.0, "I": 3722.1, "J": 5577.9, "K": 3278.1, "L": 3603.0},
        5.0:  {"A": 2042.6, "B": 2562.6, "E": 2601.9, "F": 3903.1, "G": 4269.1, "H": 2634.0, "I": 3984.3, "J": 5953.5, "K": 3440.7, "L": 3844.2},
        5.5:  {"A": 2054.6, "B": 3001.2, "E": 2892.6, "F": 4124.7, "G": 4696.1, "H": 2643.2, "I": 4065.9, "J": 6436.7, "K": 3462.1, "L": 4247.9},
        6.0:  {"A": 2134.0, "B": 3111.4, "E": 3040.1, "F": 4346.3, "G": 4972.4, "H": 2792.2, "I": 4301.7, "J": 6816.3, "K": 3595.7, "L": 4497.5},
        6.5:  {"A": 2213.3, "B": 3221.6, "E": 3187.7, "F": 4567.9, "G": 5248.7, "H": 2941.2, "I": 4537.5, "J": 7196.0, "K": 3729.3, "L": 4747.0},
        7.0:  {"A": 2292.7, "B": 3331.9, "E": 3335.2, "F": 4789.5, "G": 5525.1, "H": 3090.2, "I": 4773.3, "J": 7575.7, "K": 3862.9, "L": 4996.5},
        7.5:  {"A": 2372.0, "B": 3442.1, "E": 3482.8, "F": 5011.0, "G": 5801.4, "H": 3239.2, "I": 5009.1, "J": 7955.3, "K": 3996.5, "L": 5246.1},
        8.0:  {"A": 2451.3, "B": 3552.3, "E": 3630.3, "F": 5232.6, "G": 6077.7, "H": 3388.2, "I": 5244.9, "J": 8335.0, "K": 4130.2, "L": 5495.6},
        8.5:  {"A": 2530.7, "B": 3662.5, "E": 3777.9, "F": 5454.2, "G": 6354.0, "H": 3537.2, "I": 5480.7, "J": 8714.7, "K": 4263.8, "L": 5745.1},
        9.0:  {"A": 2610.0, "B": 3772.7, "E": 3925.4, "F": 5675.8, "G": 6630.4, "H": 3686.2, "I": 5716.5, "J": 9094.3, "K": 4397.4, "L": 5994.7},
        9.5:  {"A": 2689.4, "B": 3882.9, "E": 4073.0, "F": 5897.4, "G": 6906.7, "H": 3835.2, "I": 5952.3, "J": 9474.0, "K": 4531.0, "L": 6244.2},
        10.0: {"A": 2768.7, "B": 3993.1, "E": 4220.5, "F": 6119.0, "G": 7183.0, "H": 3984.2, "I": 6188.1, "J": 9853.7, "K": 4664.6, "L": 6493.8},
        10.5: {"A": 3038.5, "B": 4737.6, "E": 4748.1, "F": 6125.8, "G": 7259.4, "H": 4324.3, "I": 7327.7, "J":10747.1, "K": 5117.0, "L": 7233.6},
        11.0: {"A": 3116.0, "B": 4867.4, "E": 4910.8, "F": 6341.8, "G": 7528.1, "H": 4450.6, "I": 7597.5, "J":11147.1, "K": 5247.4, "L": 7501.8},
        11.5: {"A": 3193.5, "B": 4997.2, "E": 5073.5, "F": 6557.8, "G": 7796.7, "H": 4576.9, "I": 7867.3, "J":11547.1, "K": 5377.9, "L": 7769.9},
        12.0: {"A": 3271.0, "B": 5126.9, "E": 5236.2, "F": 6773.8, "G": 8065.4, "H": 4703.2, "I": 8137.1, "J":11947.1, "K": 5508.3, "L": 8038.1},
        12.5: {"A": 3348.5, "B": 5256.7, "E": 5398.9, "F": 6989.8, "G": 8334.1, "H": 4829.5, "I": 8406.8, "J":12347.1, "K": 5638.7, "L": 8306.2},
        13.0: {"A": 3426.0, "B": 5386.5, "E": 5561.6, "F": 7205.8, "G": 8602.8, "H": 4955.8, "I": 8676.6, "J":12747.1, "K": 5769.2, "L": 8574.4},
        13.5: {"A": 3503.5, "B": 5516.3, "E": 5724.3, "F": 7421.7, "G": 8871.5, "H": 5082.1, "I": 8946.4, "J":13147.1, "K": 5899.6, "L": 8842.5},
        14.0: {"A": 3581.0, "B": 5646.1, "E": 5887.0, "F": 7637.7, "G": 9140.2, "H": 5208.4, "I": 9216.2, "J":13547.1, "K": 6030.1, "L": 9110.6},
        14.5: {"A": 3658.4, "B": 5775.9, "E": 6049.7, "F": 7853.7, "G": 9408.9, "H": 5334.7, "I": 9486.0, "J":13947.1, "K": 6160.5, "L": 9378.8},
        15.0: {"A": 3735.9, "B": 5905.7, "E": 6212.4, "F": 8069.7, "G": 9677.6, "H": 5461.0, "I": 9755.8, "J":14347.1, "K": 6290.9, "L": 9646.9},
        15.5: {"A": 3813.4, "B": 6035.5, "E": 6375.1, "F": 8285.7, "G": 9946.3, "H": 5587.2, "I":10025.6, "J":14747.1, "K": 6421.4, "L": 9915.1},
        16.0: {"A": 3890.9, "B": 6165.2, "E": 6537.8, "F": 8501.7, "G":10214.9, "H": 5713.5, "I":10295.4, "J":15147.1, "K": 6551.8, "L":10183.2},
        16.5: {"A": 3968.4, "B": 6295.0, "E": 6700.5, "F": 8717.7, "G":10483.6, "H": 5839.8, "I":10565.2, "J":15547.1, "K": 6682.3, "L":10451.4},
        17.0: {"A": 4045.9, "B": 6424.8, "E": 6863.2, "F": 8933.7, "G":10752.3, "H": 5966.1, "I":10834.9, "J":15947.1, "K": 6812.7, "L":10719.5},
        17.5: {"A": 4123.4, "B": 6554.6, "E": 7025.9, "F": 9149.7, "G":11021.0, "H": 6092.4, "I":11104.7, "J":16347.1, "K": 6943.1, "L":10987.7},
        18.0: {"A": 4200.9, "B": 6684.4, "E": 7188.6, "F": 9365.7, "G":11289.7, "H": 6218.7, "I":11374.5, "J":16747.1, "K": 7073.6, "L":11255.8},
        18.5: {"A": 4278.4, "B": 6814.2, "E": 7351.3, "F": 9581.7, "G":11558.4, "H": 6345.0, "I":11644.3, "J":17147.1, "K": 7204.0, "L":11523.9},
        19.0: {"A": 4355.8, "B": 6944.0, "E": 7514.0, "F": 9797.7, "G":11827.1, "H": 6471.3, "I":11914.1, "J":17547.1, "K": 7334.4, "L":11792.1},
        19.5: {"A": 4433.3, "B": 7073.8, "E": 7676.7, "F":10013.7, "G":12095.8, "H": 6597.6, "I":12183.9, "J":17947.1, "K": 7464.9, "L":12060.2},
        20.0: {"A": 4510.8, "B": 7203.5, "E": 7839.4, "F":10229.6, "G":12364.4, "H": 6723.9, "I":12453.7, "J":18347.1, "K": 7595.3, "L":12328.4},
        20.5: {"A": 4588.3, "B": 7333.3, "E": 8002.1, "F":10445.6, "G":12633.1, "H": 6850.2, "I":12723.5, "J":18747.1, "K": 7725.8, "L":12596.5},
        # 21 – 70.5 kg (Section 1d)
        21.0: {"A": 5884.9, "B":10146.4, "E":10167.6, "F":10458.6, "G":13170.2, "H": 8286.4, "I":14050.8, "J":21785.5, "K": 9798.3, "L":16216.6},
        21.5: {"A": 5977.9, "B":10318.2, "E":10361.8, "F":10661.2, "G":13433.4, "H": 8429.5, "I":14330.9, "J":22219.7, "K": 9953.1, "L":16540.1},
        22.0: {"A": 6070.9, "B":10490.0, "E":10556.1, "F":10863.7, "G":13696.7, "H": 8572.7, "I":14610.9, "J":22653.9, "K":10107.8, "L":16863.7},
        22.5: {"A": 6163.8, "B":10661.8, "E":10750.3, "F":11066.3, "G":13959.9, "H": 8715.8, "I":14890.9, "J":23088.1, "K":10262.6, "L":17187.2},
        23.0: {"A": 6256.8, "B":10833.6, "E":10944.6, "F":11268.8, "G":14223.2, "H": 8859.0, "I":15171.0, "J":23522.3, "K":10417.3, "L":17510.7},
        23.5: {"A": 6349.8, "B":11005.4, "E":11138.8, "F":11471.4, "G":14486.4, "H": 9002.1, "I":15451.0, "J":23956.5, "K":10572.0, "L":17834.3},
        24.0: {"A": 6442.7, "B":11177.2, "E":11333.1, "F":11673.9, "G":14749.6, "H": 9145.2, "I":15731.0, "J":24390.7, "K":10726.8, "L":18157.8},
        24.5: {"A": 6535.7, "B":11349.0, "E":11527.3, "F":11876.5, "G":15012.9, "H": 9288.4, "I":16011.0, "J":24824.9, "K":10881.5, "L":18481.3},
        25.0: {"A": 6628.7, "B":11520.8, "E":11721.6, "F":12079.0, "G":15276.1, "H": 9431.5, "I":16291.1, "J":25259.1, "K":11036.3, "L":18804.9},
        25.5: {"A": 6721.6, "B":11692.6, "E":11915.9, "F":12281.6, "G":15539.3, "H": 9574.7, "I":16571.1, "J":25693.2, "K":11191.0, "L":19128.4},
        26.0: {"A": 6814.6, "B":11864.4, "E":12110.1, "F":12484.1, "G":15802.6, "H": 9717.8, "I":16851.1, "J":26127.4, "K":11345.8, "L":19451.9},
        26.5: {"A": 6907.6, "B":12036.2, "E":12304.4, "F":12686.7, "G":16065.8, "H": 9861.0, "I":17131.2, "J":26561.6, "K":11500.5, "L":19775.4},
        27.0: {"A": 7000.5, "B":12208.0, "E":12498.6, "F":12889.2, "G":16329.1, "H":10004.1, "I":17411.2, "J":26995.8, "K":11655.3, "L":20099.0},
        27.5: {"A": 7093.5, "B":12379.8, "E":12692.9, "F":13091.8, "G":16592.3, "H":10147.3, "I":17691.2, "J":27430.0, "K":11810.0, "L":20422.5},
        28.0: {"A": 7186.5, "B":12551.6, "E":12887.1, "F":13294.3, "G":16855.5, "H":10290.4, "I":17971.3, "J":27864.2, "K":11964.7, "L":20746.0},
        28.5: {"A": 7279.4, "B":12723.4, "E":13081.4, "F":13496.9, "G":17118.8, "H":10433.6, "I":18251.3, "J":28298.4, "K":12119.5, "L":21069.6},
        29.0: {"A": 7372.4, "B":12895.2, "E":13275.7, "F":13699.4, "G":17382.0, "H":10576.7, "I":18531.3, "J":28732.6, "K":12274.2, "L":21393.1},
        29.5: {"A": 7465.4, "B":13067.0, "E":13469.9, "F":13902.0, "G":17645.2, "H":10719.9, "I":18811.4, "J":29166.8, "K":12429.0, "L":21716.6},
        30.0: {"A": 7558.3, "B":13238.8, "E":13664.2, "F":14104.5, "G":17908.5, "H":10863.0, "I":19091.4, "J":29601.0, "K":12583.7, "L":22040.2},
        30.5: {"A": 7651.3, "B":13410.6, "E":13858.4, "F":14307.1, "G":18171.7, "H":11006.2, "I":19371.4, "J":30035.2, "K":12738.5, "L":22363.7},
        31.0: {"A": 7744.3, "B":13582.4, "E":14052.7, "F":14509.6, "G":18435.0, "H":11149.3, "I":19651.5, "J":30469.4, "K":12893.2, "L":22687.2},
        31.5: {"A": 7837.2, "B":13754.2, "E":14246.9, "F":14712.2, "G":18698.2, "H":11292.5, "I":19931.5, "J":30903.6, "K":13047.9, "L":23010.7},
        32.0: {"A": 7930.2, "B":13926.0, "E":14441.2, "F":14914.7, "G":18961.4, "H":11435.6, "I":20211.5, "J":31337.8, "K":13202.7, "L":23334.3},
        32.5: {"A": 8023.2, "B":14097.8, "E":14635.4, "F":15117.3, "G":19224.7, "H":11578.8, "I":20491.6, "J":31772.0, "K":13357.4, "L":23657.8},
        33.0: {"A": 8116.1, "B":14269.6, "E":14829.7, "F":15319.8, "G":19487.9, "H":11721.9, "I":20771.6, "J":32206.2, "K":13512.2, "L":23981.3},
        33.5: {"A": 8209.1, "B":14441.4, "E":15024.0, "F":15522.4, "G":19751.1, "H":11865.0, "I":21051.6, "J":32640.4, "K":13666.9, "L":24304.9},
        34.0: {"A": 8302.1, "B":14613.2, "E":15218.2, "F":15724.9, "G":20014.4, "H":12008.2, "I":21331.7, "J":33074.6, "K":13821.7, "L":24628.4},
        34.5: {"A": 8395.0, "B":14785.0, "E":15412.5, "F":15927.5, "G":20277.6, "H":12151.3, "I":21611.7, "J":33508.8, "K":13976.4, "L":24951.9},
        35.0: {"A": 8488.0, "B":14956.8, "E":15606.7, "F":16130.0, "G":20540.9, "H":12294.5, "I":21891.7, "J":33943.0, "K":14131.2, "L":25275.4},
        35.5: {"A": 8581.0, "B":15128.6, "E":15801.0, "F":16332.6, "G":20804.1, "H":12437.6, "I":22171.7, "J":34377.2, "K":14285.9, "L":25599.0},
        36.0: {"A": 8673.9, "B":15300.4, "E":15995.2, "F":16535.1, "G":21067.3, "H":12580.8, "I":22451.8, "J":34811.4, "K":14440.6, "L":25922.5},
        36.5: {"A": 8766.9, "B":15472.2, "E":16189.5, "F":16737.7, "G":21330.6, "H":12723.9, "I":22731.8, "J":35245.6, "K":14595.4, "L":26246.0},
        37.0: {"A": 8859.9, "B":15644.0, "E":16383.7, "F":16940.2, "G":21593.8, "H":12867.1, "I":23011.8, "J":35679.8, "K":14750.1, "L":26569.6},
        37.5: {"A": 8952.8, "B":15815.8, "E":16578.0, "F":17142.8, "G":21857.0, "H":13010.2, "I":23291.9, "J":36114.0, "K":14904.9, "L":26893.1},
        38.0: {"A": 9045.8, "B":15987.6, "E":16772.3, "F":17345.3, "G":22120.3, "H":13153.4, "I":23571.9, "J":36548.2, "K":15059.6, "L":27216.6},
        38.5: {"A": 9138.8, "B":16159.4, "E":16966.5, "F":17547.9, "G":22383.5, "H":13296.5, "I":23851.9, "J":36982.4, "K":15214.4, "L":27540.2},
        39.0: {"A": 9231.7, "B":16331.2, "E":17160.8, "F":17750.4, "G":22646.7, "H":13439.7, "I":24132.0, "J":37416.6, "K":15369.1, "L":27863.7},
        39.5: {"A": 9324.7, "B":16503.0, "E":17355.0, "F":17953.0, "G":22910.0, "H":13582.8, "I":24412.0, "J":37850.8, "K":15523.9, "L":28187.2},
        40.0: {"A": 9417.7, "B":16674.8, "E":17549.3, "F":18155.5, "G":23173.2, "H":13726.0, "I":24692.0, "J":38285.0, "K":15678.6, "L":28510.7},
        40.5: {"A": 9510.6, "B":16846.6, "E":17743.5, "F":18358.1, "G":23436.5, "H":13869.1, "I":24972.1, "J":38719.2, "K":15833.3, "L":28834.3},
        41.0: {"A": 9603.6, "B":17018.4, "E":17937.8, "F":18560.6, "G":23699.7, "H":14012.3, "I":25252.1, "J":39153.4, "K":15988.1, "L":29157.8},
        41.5: {"A": 9696.6, "B":17190.2, "E":18132.1, "F":18763.2, "G":23962.9, "H":14155.4, "I":25532.1, "J":39587.6, "K":16142.8, "L":29481.3},
        42.0: {"A": 9789.5, "B":17362.0, "E":18326.3, "F":18965.7, "G":24226.2, "H":14298.6, "I":25812.2, "J":40021.8, "K":16297.6, "L":29804.9},
        42.5: {"A": 9882.5, "B":17533.8, "E":18520.6, "F":19168.3, "G":24489.4, "H":14441.7, "I":26092.2, "J":40456.0, "K":16452.3, "L":30128.4},
        43.0: {"A": 9975.5, "B":17705.6, "E":18714.8, "F":19370.8, "G":24752.6, "H":14584.8, "I":26372.2, "J":40890.2, "K":16607.1, "L":30451.9},
        43.5: {"A":10068.4, "B":17877.4, "E":18909.1, "F":19573.4, "G":25015.9, "H":14728.0, "I":26652.3, "J":41324.4, "K":16761.8, "L":30775.5},
        44.0: {"A":10161.4, "B":18049.2, "E":19103.3, "F":19775.9, "G":25279.1, "H":14871.1, "I":26932.3, "J":41758.6, "K":16916.5, "L":31099.0},
        44.5: {"A":10254.4, "B":18221.0, "E":19297.6, "F":19978.5, "G":25542.4, "H":15014.3, "I":27212.3, "J":42192.8, "K":17071.3, "L":31422.5},
        45.0: {"A":11372.2, "B":20944.1, "E":20567.2, "F":20206.6, "G":26677.2, "H":16655.2, "I":29660.4, "J":44733.7, "K":18615.2, "L":33427.8},
        45.5: {"A":11475.2, "B":21140.7, "E":20767.7, "F":20407.1, "G":26947.1, "H":16810.8, "I":29956.2, "J":45185.3, "K":18783.9, "L":33767.2},
        46.0: {"A":11578.3, "B":21337.4, "E":20968.2, "F":20607.5, "G":27216.9, "H":16966.3, "I":30251.9, "J":45636.9, "K":18952.5, "L":34106.6},
        46.5: {"A":11681.3, "B":21534.0, "E":21168.7, "F":20808.0, "G":27486.8, "H":17121.9, "I":30547.6, "J":46088.5, "K":19121.2, "L":34446.0},
        47.0: {"A":11784.4, "B":21730.6, "E":21369.3, "F":21008.4, "G":27756.7, "H":17277.5, "I":30843.3, "J":46540.1, "K":19289.9, "L":34785.4},
        47.5: {"A":11887.5, "B":21927.3, "E":21569.8, "F":21208.9, "G":28026.5, "H":17433.0, "I":31139.1, "J":46991.7, "K":19458.5, "L":35124.8},
        48.0: {"A":11990.5, "B":22123.9, "E":21770.3, "F":21409.3, "G":28296.4, "H":17588.6, "I":31434.8, "J":47443.3, "K":19627.2, "L":35464.3},
        48.5: {"A":12093.6, "B":22320.5, "E":21970.8, "F":21609.8, "G":28566.3, "H":17744.2, "I":31730.5, "J":47894.9, "K":19795.8, "L":35803.7},
        49.0: {"A":12196.6, "B":22517.1, "E":22171.3, "F":21810.2, "G":28836.2, "H":17899.7, "I":32026.2, "J":48346.5, "K":19964.5, "L":36143.1},
        49.5: {"A":12299.7, "B":22713.8, "E":22371.9, "F":22010.7, "G":29106.0, "H":18055.3, "I":32322.0, "J":48798.0, "K":20133.2, "L":36482.5},
        50.0: {"A":12402.7, "B":22910.4, "E":22572.4, "F":22211.1, "G":29375.9, "H":18210.8, "I":32617.7, "J":49249.6, "K":20301.8, "L":36821.9},
        50.5: {"A":12505.8, "B":23107.0, "E":22772.9, "F":22411.5, "G":29645.8, "H":18366.4, "I":32913.4, "J":49701.2, "K":20470.5, "L":37161.3},
        51.0: {"A":12608.8, "B":23303.7, "E":22973.4, "F":22612.0, "G":29915.6, "H":18522.0, "I":33209.1, "J":50152.8, "K":20639.2, "L":37500.7},
        51.5: {"A":12711.9, "B":23500.3, "E":23174.0, "F":22812.4, "G":30185.5, "H":18677.5, "I":33504.9, "J":50604.4, "K":20807.8, "L":37840.1},
        52.0: {"A":12814.9, "B":23696.9, "E":23374.5, "F":23012.9, "G":30455.4, "H":18833.1, "I":33800.6, "J":51056.0, "K":20976.5, "L":38179.5},
        52.5: {"A":12918.0, "B":23893.6, "E":23575.0, "F":23213.3, "G":30725.3, "H":18988.7, "I":34096.3, "J":51507.6, "K":21145.2, "L":38518.9},
        53.0: {"A":13021.1, "B":24090.2, "E":23775.5, "F":23413.8, "G":30995.1, "H":19144.2, "I":34392.0, "J":51959.2, "K":21313.8, "L":38858.4},
        53.5: {"A":13124.1, "B":24286.8, "E":23976.0, "F":23614.2, "G":31265.0, "H":19299.8, "I":34687.8, "J":52410.8, "K":21482.5, "L":39197.8},
        54.0: {"A":13227.2, "B":24483.5, "E":24176.6, "F":23814.7, "G":31534.9, "H":19455.4, "I":34983.5, "J":52862.4, "K":21651.2, "L":39537.2},
        54.5: {"A":13330.2, "B":24680.1, "E":24377.1, "F":24015.1, "G":31804.7, "H":19610.9, "I":35279.2, "J":53314.0, "K":21819.8, "L":39876.6},
        55.0: {"A":13433.3, "B":24876.7, "E":24577.6, "F":24215.6, "G":32074.6, "H":19766.5, "I":35574.9, "J":53765.6, "K":21988.5, "L":40216.0},
        55.5: {"A":13536.3, "B":25073.4, "E":24778.1, "F":24416.0, "G":32344.5, "H":19922.1, "I":35870.7, "J":54217.2, "K":22157.1, "L":40555.4},
        56.0: {"A":13639.4, "B":25270.0, "E":24978.7, "F":24616.5, "G":32614.4, "H":20077.6, "I":36166.4, "J":54668.8, "K":22325.8, "L":40894.8},
        56.5: {"A":13742.4, "B":25466.6, "E":25179.2, "F":24816.9, "G":32884.2, "H":20233.2, "I":36462.1, "J":55120.4, "K":22494.5, "L":41234.2},
        57.0: {"A":13845.5, "B":25663.3, "E":25379.7, "F":25017.4, "G":33154.1, "H":20388.8, "I":36757.8, "J":55572.0, "K":22663.1, "L":41573.6},
        57.5: {"A":13948.5, "B":25859.9, "E":25580.2, "F":25217.8, "G":33424.0, "H":20544.3, "I":37053.6, "J":56023.6, "K":22831.8, "L":41913.1},
        58.0: {"A":14051.6, "B":26056.5, "E":25780.7, "F":25418.3, "G":33693.8, "H":20699.9, "I":37349.3, "J":56475.1, "K":23000.5, "L":42252.5},
        58.5: {"A":14154.7, "B":26253.2, "E":25981.3, "F":25618.7, "G":33963.7, "H":20855.4, "I":37645.0, "J":56926.7, "K":23169.1, "L":42591.9},
        59.0: {"A":14257.7, "B":26449.8, "E":26181.8, "F":25819.2, "G":34233.6, "H":21011.0, "I":37940.7, "J":57378.3, "K":23337.8, "L":42931.3},
        59.5: {"A":14360.8, "B":26646.4, "E":26382.3, "F":26019.6, "G":34503.5, "H":21166.6, "I":38236.5, "J":57829.9, "K":23506.5, "L":43270.7},
        60.0: {"A":14463.8, "B":26843.1, "E":26582.8, "F":26220.0, "G":34773.3, "H":21322.1, "I":38532.2, "J":58281.5, "K":23675.1, "L":43610.1},
        60.5: {"A":14566.9, "B":27039.7, "E":26783.3, "F":26420.5, "G":35043.2, "H":21477.7, "I":38827.9, "J":58733.1, "K":23843.8, "L":43949.5},
        61.0: {"A":14669.9, "B":27236.3, "E":26983.9, "F":26620.9, "G":35313.1, "H":21633.3, "I":39123.6, "J":59184.7, "K":24012.4, "L":44288.9},
        61.5: {"A":14773.0, "B":27433.0, "E":27184.4, "F":26821.4, "G":35582.9, "H":21788.8, "I":39419.4, "J":59636.3, "K":24181.1, "L":44628.3},
        62.0: {"A":14876.0, "B":27629.6, "E":27384.9, "F":27021.8, "G":35852.8, "H":21944.4, "I":39715.1, "J":60087.9, "K":24349.8, "L":44967.7},
        62.5: {"A":14979.1, "B":27826.2, "E":27585.4, "F":27222.3, "G":36122.7, "H":22100.0, "I":40010.8, "J":60539.5, "K":24518.4, "L":45307.2},
        63.0: {"A":15082.1, "B":28022.9, "E":27786.0, "F":27422.7, "G":36392.5, "H":22255.5, "I":40306.5, "J":60991.1, "K":24687.1, "L":45646.6},
        63.5: {"A":15185.2, "B":28219.5, "E":27986.5, "F":27623.2, "G":36662.4, "H":22411.1, "I":40602.3, "J":61442.7, "K":24855.8, "L":45986.0},
        64.0: {"A":15288.3, "B":28416.1, "E":28187.0, "F":27823.6, "G":36932.3, "H":22566.7, "I":40898.0, "J":61894.3, "K":25024.4, "L":46325.4},
        64.5: {"A":15391.3, "B":28612.8, "E":28387.5, "F":28024.1, "G":37202.2, "H":22722.2, "I":41193.7, "J":62345.9, "K":25193.1, "L":46664.8},
        65.0: {"A":15494.4, "B":28809.4, "E":28588.0, "F":28224.5, "G":37472.0, "H":22877.8, "I":41489.4, "J":62797.5, "K":25361.8, "L":47004.2},
        65.5: {"A":15597.4, "B":29006.0, "E":28788.6, "F":28425.0, "G":37741.9, "H":23033.4, "I":41785.2, "J":63249.1, "K":25530.4, "L":47343.6},
        66.0: {"A":15700.5, "B":29202.7, "E":28989.1, "F":28625.4, "G":38011.8, "H":23188.9, "I":42080.9, "J":63700.6, "K":25699.1, "L":47683.0},
        66.5: {"A":15803.5, "B":29399.3, "E":29189.6, "F":28825.9, "G":38281.6, "H":23344.5, "I":42376.6, "J":64152.2, "K":25867.8, "L":48022.4},
        67.0: {"A":15906.6, "B":29595.9, "E":29390.1, "F":29026.3, "G":38551.5, "H":23500.1, "I":42672.3, "J":64603.8, "K":26036.4, "L":48361.9},
        67.5: {"A":16009.6, "B":29792.6, "E":29590.6, "F":29226.8, "G":38821.4, "H":23655.6, "I":42968.1, "J":65055.4, "K":26205.1, "L":48701.3},
        68.0: {"A":16112.7, "B":29989.2, "E":29791.2, "F":29427.2, "G":39091.3, "H":23811.2, "I":43263.8, "J":65507.0, "K":26373.7, "L":49040.7},
        68.5: {"A":16215.7, "B":30185.8, "E":29991.7, "F":29627.7, "G":39361.1, "H":23966.7, "I":43559.5, "J":65958.6, "K":26542.4, "L":49380.1},
        69.0: {"A":16318.8, "B":30382.5, "E":30192.2, "F":29828.1, "G":39631.0, "H":24122.3, "I":43855.2, "J":66410.2, "K":26711.1, "L":49719.5},
        69.5: {"A":16421.9, "B":30579.1, "E":30392.7, "F":30028.6, "G":39900.9, "H":24277.9, "I":44151.0, "J":66861.8, "K":26879.7, "L":50058.9},
        70.0: {"A":16524.9, "B":30775.7, "E":30593.3, "F":30229.0, "G":40170.7, "H":24433.4, "I":44446.7, "J":67313.4, "K":27048.4, "L":50398.3},
        70.5: {"A":16628.0, "B":30972.4, "E":30793.8, "F":30429.4, "G":40440.6, "H":24589.0, "I":44742.4, "J":67765.0, "K":27217.1, "L":50737.7},
    },
}


# ------------------------------------------------------------------
# 1G.  UPS ZONE MAP  (PDF Section 6 — complete country list)
# ------------------------------------------------------------------
# country (lowercase) → zone code string "01"–"10" (Express Saver Import)
# "-" destinations are not serviceable; stored as None.

STATIC_UPS_ZONE_MAP = {
    "afghanistan":                   "09",
    "aland island (finland)":        "07",
    "albania":                       "09",
    "algeria":                       "09",
    "american samoa":                "08",
    "angola":                        "08",
    "anguilla":                      "08",
    "antigua and barbuda":           "08",
    "argentina":                     "08",
    "armenia":                       "09",
    "aruba":                         "08",
    "australia":                     "02",
    "austria":                       "06",
    "azerbaijan":                    "09",
    "azores (portugal)":             "07",
    "bahamas":                       "08",
    "bahrain":                       "03",
    "bangladesh":                    "03",
    "barbados":                      "08",
    "belarus":                       "09",
    "byelorussia":                   "09",
    "belgium":                       "06",
    "benin":                         "09",
    "bermuda":                       "08",
    "bhutan":                        "08",
    "bolivia":                       "08",
    "bonaire, st. eustatius, saba":  "08",
    "bosnia and herzegovina":        "09",
    "botswana":                      "09",
    "brazil":                        "08",
    "british virgin islands":        "08",
    "brunei":                        "08",
    "bulgaria":                      "08",
    "burkina faso":                  "09",
    "burundi":                       "09",
    "cambodia":                      "08",
    "cameroon":                      "08",
    "campione/ lake lugano (italy)": "06",
    "canada":                        "05",
    "canary islands (spain)":        "06",
    "cape verde":                    "09",
    "cayman islands":                "08",
    "chad":                          "09",
    # China has postal-code-based zones; default main zone = "04"
    "china":                         "04",
    "colombia":                      "08",
    "comoros":                       "09",
    "congo (brazzaville)":           "09",
    "congo, democratic republic of": "09",
    "costa rica":                    "08",
    "cote d'ivoire (ivory coast)":   "08",
    "ivory coast":                   "08",
    "croatia":                       "09",
    "cuba":                          "08",
    "curacao":                       "08",
    "cyprus":                        "08",
    "czech republic":                "08",
    "denmark":                       "07",
    "djibouti":                      "09",
    "dominica":                      "08",
    "dominican republic":            "08",
    "ecuador":                       "08",
    "egypt":                         "08",
    "el salvador":                   "08",
    "england (united kingdom)":      "06",
    "eritrea":                       "09",
    "estonia":                       "09",
    "ethiopia":                      "08",
    "fiji":                          "08",
    "finland":                       "07",
    "france":                        "06",
    "french polynesia":              "08",
    "gabon":                         "09",
    "gambia":                        "09",
    "georgia":                       "09",
    "germany":                       "06",
    "ghana":                         "08",
    "gibraltar":                     "08",
    "greece":                        "06",
    "grenada":                       "08",
    "guadeloupe":                    "08",
    "guam":                          "08",
    "guatemala":                     "08",
    "guernsey (channel islands)":    "07",
    "guinea":                        "09",
    "guinea-bissau":                 "09",
    "guyana":                        "08",
    "haiti":                         "08",
    "heligoland (germany)":          "06",
    "honduras":                      "08",
    "hong kong sar, china":          "02",
    "hong kong sar":                 "02",
    "hungary":                       "08",
    "iceland":                       "08",
    "indonesia":                     "04",
    "iraq":                          "09",
    "ireland, republic of":          "06",
    "ireland":                       "06",
    "israel":                        "08",
    "italy":                         "06",
    "jamaica":                       "08",
    "japan":                         "04",
    "jersey (channel islands)":      "07",
    "jordan":                        "03",
    "kazakhstan":                    "09",
    "kenya":                         "08",
    "kirghizia (kyrgyzstan)":        "09",
    "kyrgyzstan":                    "09",
    "korea, south":                  "04",
    "south korea":                   "04",
    "kosovo":                        "09",
    "kuwait":                        "03",
    "laos":                          "08",
    "latvia":                        "09",
    "lebanon":                       "03",
    "lesotho":                       "09",
    "liberia":                       "09",
    "libyan arab jamahiriya":        "09",
    "libya":                         "09",
    "liechtenstein":                 "07",
    "lithuania":                     "09",
    "livigno (italy)":               "06",
    "luxembourg":                    "06",
    "macau sar, china":              "02",
    "macau sar":                     "02",
    "macao sar, china":              "02",
    "macedonia (fyrom)":             "09",
    "north macedonia":               "09",
    "madagascar":                    "08",
    "madeira (portugal)":            "07",
    "malawi":                        "09",
    "malaysia":                      "03",
    "maldives":                      "06",
    "mali":                          "09",
    "malta":                         "08",
    "martinique":                    "08",
    "mauritania":                    "08",
    "mauritius":                     "09",
    "mayotte":                       "09",
    "mexico":                        "05",
    "moldova":                       "09",
    "monaco (france)":               "06",
    "monaco":                        "06",
    "mongolia":                      "08",
    "montenegro":                    "09",
    "montserrat":                    "08",
    "morocco":                       "08",
    "mount athos (greece)":          "06",
    "mozambique":                    "09",
    "myanmar":                       "08",
    "namibia":                       "09",
    "nepal":                         "01",
    "netherlands (holland)":         "06",
    "netherlands":                   "06",
    "new caledonia":                 "07",
    "new zealand":                   "03",
    "nicaragua":                     "08",
    "niger":                         "09",
    "nigeria":                       "09",
    "northern ireland (united kingdom)": "06",
    "northern mariana islands":      "07",
    "norway":                        "07",
    "oman":                          "03",
    "pakistan":                      "01",
    "panama":                        "08",
    "paraguay":                      "08",
    "peru":                          "09",
    "philippines":                   "01",
    "poland":                        "08",
    "portugal":                      "07",
    "puerto rico":                   "05",
    "qatar":                         "03",
    "reunion island":                "08",
    "romania":                       "08",
    "russia":                        "09",
    "rwanda":                        "09",
    "samoa":                         "08",
    "san marino":                    "06",
    "saudi arabia":                  "03",
    "scotland (united kingdom)":     "06",
    "senegal":                       "08",
    "serbia":                        "09",
    "seychelles":                    "09",
    "sierra leone":                  "09",
    "singapore":                     "01",
    "slovakia":                      "08",
    "slovenia":                      "09",
    "south africa":                  "08",
    "spain":                         "06",
    "sri lanka":                     "01",
    "st. kitts and nevis":           "08",
    "st. lucia":                     "08",
    "st. vincent & the grenadines":  "08",
    "suriname":                      "08",
    "swaziland":                     "09",
    "sweden":                        "07",
    "switzerland":                   "07",
    "syrian arab republic":          "08",
    "syria":                         "08",
    "taiwan, china":                 "02",
    "taiwan":                        "02",
    "tanzania, united republic of":  "08",
    "tanzania":                      "08",
    "thailand":                      "01",
    "togo":                          "09",
    "trinidad & tobago":             "08",
    "trinidad and tobago":           "08",
    "tunisia":                       "09",
    "turkey":                        "08",
    "turkmenistan":                  "09",
    "turks & caicos islands":        "07",
    "u.s. virgin islands":           "08",
    "uganda":                        "08",
    "ukraine":                       "09",
    "united arab emirates":          "02",
    "united arab emirate":           "02",
    "uae":                           "02",
    "united kingdom":                "06",
    "great britain":                 "06",
    "uk":                            "06",
    "united states":                 "05",
    "usa":                           "05",
    "u.s.a.":                        "05",
    "us":                            "05",
    "uruguay":                       "08",
    "uzbekistan":                    "09",
    "vatican city (italy)":          "06",
    "venezuela":                     "08",
    "vietnam":                       "02",
    "viet nam":                      "02",
    "wales (united kingdom)":        "06",
    "yemen, republic of":            "03",
    "zambia":                        "09",
    "zimbabwe":                      "09",
}

STATIC_UPS_VOLUMETRIC_DIVISOR = 5000   # cm³ ÷ 5000 = vol weight kg


# ------------------------------------------------------------------
# 1H.  UPS FREIGHT RATE TABLE  (PDF Sections 5a, 5b, 5c)
# ------------------------------------------------------------------
# Structure:
#   STATIC_UPS_RATES[package_type][weight_key] = {zone_str: rate_inr, ...}
#
# package_type : "LTR" | "Doc" | "NDC"
# weight_key   : float for exact slabs (0.5–20) | str for bulk ranges
# zone_str     : "01"–"10"
#
# Bulk ranges (21+ kg) store per-kg rates as strings matching the PDF bands.

STATIC_UPS_RATES = {

    # ── 5a. Letter / Document (flat per zone, same rate) ────────────────
    "LTR": {
        0.5: {"01": 1711.1, "02": 2698.0, "03": 3184.3, "04": 2476.5, "05": 4703.8,
              "06": 4826.6, "07": 8352.4, "08": 8348.2, "09": 5746.7, "10": 2377.1},
    },
    "Doc": {
        0.5: {"01": 1711.1, "02": 2698.0, "03": 3184.3, "04": 2476.5, "05": 4703.8,
              "06": 4826.6, "07": 8352.4, "08": 8348.2, "09": 5746.7, "10": 2377.1},
    },

    # ── 5b. NDC — Non-Document Courier (0.5–20 kg) ──────────────────────
    "NDC": {
        # exact kg slabs
        0.5:  {"01":  2634.8, "02":  1066.9, "03":  8209.7, "04":   748.8, "05":  1687.4, "06":  2130.5, "07": 11034.1, "08":  9286.1, "09":  7556.5, "10":   717.9},
        1.0:  {"01":  3473.3, "02":  1242.3, "03":  9373.4, "04":   945.3, "05":  1958.6, "06":  2446.1, "07": 13681.7, "08": 10757.9, "09":  8698.2, "10":   907.9},
        1.5:  {"01":  4317.5, "02":  1417.6, "03": 10531.4, "04":  1142.7, "05":  2228.2, "06":  2761.3, "07": 15406.3, "08": 12233.3, "09":  9838.5, "10":  1096.8},
        2.0:  {"01":  5160.3, "02":  1593.2, "03": 11693.7, "04":  1339.8, "05":  2498.6, "06":  3076.9, "07": 17128.0, "08": 13711.5, "09": 10979.4, "10":  1286.5},
        2.5:  {"01":  6004.5, "02":  1768.6, "03": 12850.3, "04":  1537.2, "05":  2769.8, "06":  3390.7, "07": 18855.5, "08": 15186.2, "09": 12118.3, "10":  1476.2},
        3.0:  {"01":  6676.8, "02":  1935.3, "03": 13930.9, "04":  1696.2, "05":  3040.8, "06":  3701.0, "07": 20220.1, "08": 16660.1, "09": 13069.7, "10":  1628.9},
        3.5:  {"01":  7347.8, "02":  2101.3, "03": 15010.8, "04":  1855.9, "05":  3312.5, "06":  4010.7, "07": 21586.8, "08": 18137.7, "09": 14020.4, "10":  1782.6},
        4.0:  {"01":  8020.2, "02":  2268.4, "03": 16090.7, "04":  2038.1, "05":  3582.2, "06":  4320.6, "07": 22950.8, "08": 19612.3, "09": 14969.6, "10":  1957.3},
        4.5:  {"01":  8691.8, "02":  2435.6, "03": 17171.3, "04":  2220.1, "05":  3854.4, "06":  4630.1, "07": 24316.1, "08": 21086.3, "09": 15917.5, "10":  2132.5},
        5.0:  {"01":  9365.6, "02":  2601.6, "03": 18254.1, "04":  2402.8, "05":  4124.9, "06":  4940.2, "07": 25685.7, "08": 22560.2, "09": 16866.8, "10":  2306.5},
        5.5:  {"01":  9870.4, "02":  2733.4, "03": 18856.2, "04":  2588.4, "05":  4414.3, "06":  5161.9, "07": 26913.3, "08": 24037.0, "09": 17654.1, "10":  2485.0},
        6.0:  {"01": 10374.5, "02":  2865.6, "03": 19463.9, "04":  2773.8, "05":  4704.0, "06":  5384.0, "07": 28141.6, "08": 25512.4, "09": 18445.1, "10":  2663.1},
        6.5:  {"01": 10792.7, "02":  2997.1, "03": 20068.9, "04":  2959.1, "05":  4994.9, "06":  5605.9, "07": 29372.0, "08": 26984.3, "09": 19236.0, "10":  2841.8},
        7.0:  {"01": 11130.0, "02":  3106.8, "03": 20675.2, "04":  3145.0, "05":  5284.1, "06":  5827.7, "07": 30601.0, "08": 28461.8, "09": 20024.8, "10":  3020.1},
        7.5:  {"01": 11470.0, "02":  3216.3, "03": 21276.6, "04":  3331.2, "05":  5574.0, "06":  6050.0, "07": 31830.7, "08": 29935.7, "09": 20813.6, "10":  3198.5},
        8.0:  {"01": 11804.5, "02":  3325.1, "03": 22036.3, "04":  3516.6, "05":  5773.0, "06":  6272.3, "07": 33017.8, "08": 30992.9, "09": 21518.7, "10":  3376.8},
        8.5:  {"01": 12141.0, "02":  3434.8, "03": 22791.7, "04":  3703.0, "05":  5972.2, "06":  6494.2, "07": 34203.5, "08": 32043.0, "09": 22221.6, "10":  3555.1},
        9.0:  {"01": 12647.9, "02":  3544.7, "03": 23546.4, "04":  3888.8, "05":  6171.1, "06":  6716.1, "07": 35389.2, "08": 33097.4, "09": 22923.1, "10":  3734.0},
        9.5:  {"01": 13152.0, "02":  3653.2, "03": 24305.4, "04":  4073.6, "05":  6370.1, "06":  6938.2, "07": 36577.1, "08": 34151.7, "09": 23626.7, "10":  3911.8},
        10.0: {"01": 13659.0, "02":  3763.1, "03": 25062.3, "04":  4260.0, "05":  6569.3, "06":  7159.8, "07": 37763.5, "08": 35204.6, "09": 24329.6, "10":  4090.2},
        10.5: {"01": 14163.1, "02":  3873.3, "03": 25566.4, "04":  4438.1, "05":  6784.3, "06":  7307.8, "07": 39231.8, "08": 36434.4, "09": 24855.0, "10":  4261.2},
        11.0: {"01": 14669.3, "02":  3982.5, "03": 26073.3, "04":  4616.8, "05":  7000.3, "06":  7455.8, "07": 40701.5, "08": 37663.4, "09": 25381.8, "10":  4432.5},
        11.5: {"01": 15173.4, "02":  4091.6, "03": 26578.1, "04":  4794.9, "05":  7213.9, "06":  7604.2, "07": 42169.0, "08": 38895.9, "09": 25912.2, "10":  4604.0},
        12.0: {"01": 15677.5, "02":  4201.3, "03": 27080.8, "04":  4973.5, "05":  7429.7, "06":  7752.0, "07": 43639.4, "08": 40125.7, "09": 26437.6, "10":  4775.6},
        12.5: {"01": 16184.4, "02":  4310.6, "03": 27502.6, "04":  5152.0, "05":  7644.2, "06":  7900.2, "07": 45109.8, "08": 41354.7, "09": 26964.4, "10":  4946.4},
        13.0: {"01": 16689.3, "02":  4420.3, "03": 27922.2, "04":  5311.2, "05":  7854.2, "06":  8048.2, "07": 46559.0, "08": 42584.4, "09": 27493.3, "10":  5100.4},
        13.5: {"01": 17193.4, "02":  4530.0, "03": 28345.3, "04":  5470.7, "05":  8063.3, "06":  8196.4, "07": 48008.8, "08": 43816.2, "09": 28021.6, "10":  5253.2},
        14.0: {"01": 17701.7, "02":  4639.2, "03": 28763.5, "04":  5630.1, "05":  8273.3, "06":  8345.6, "07": 49460.7, "08": 45048.1, "09": 28550.5, "10":  5406.2},
        14.5: {"01": 18209.4, "02":  4748.3, "03": 29181.0, "04":  5790.0, "05":  8482.8, "06":  8493.9, "07": 50912.0, "08": 46275.7, "09": 29079.5, "10":  5560.0},
        15.0: {"01": 18712.0, "02":  4858.2, "03": 29599.9, "04":  5949.5, "05":  8692.3, "06":  8642.1, "07": 52360.4, "08": 47508.2, "09": 29604.9, "10":  5712.8},
        15.5: {"01": 19215.4, "02":  4967.5, "03": 30025.9, "04":  6108.4, "05":  8902.3, "06":  8739.2, "07": 53812.3, "08": 48734.4, "09": 30133.8, "10":  5865.7},
        16.0: {"01": 19634.3, "02":  5077.4, "03": 30442.7, "04":  6268.3, "05":  9111.1, "06":  8836.7, "07": 55262.1, "08": 49964.8, "09": 30569.8, "10":  6019.5},
        16.5: {"01": 20056.8, "02":  5186.7, "03": 30863.7, "04":  6427.3, "05":  9321.4, "06":  8933.4, "07": 56712.7, "08": 51195.3, "09": 31007.1, "10":  6172.6},
        17.0: {"01": 20475.7, "02":  5295.6, "03": 31281.2, "04":  6587.7, "05":  9530.4, "06":  9029.9, "07": 58163.9, "08": 52425.7, "09": 31447.3, "10":  6325.8},
        17.5: {"01": 20946.4, "02":  5405.5, "03": 31702.2, "04":  6746.8, "05":  9739.0, "06":  9150.0, "07": 59613.7, "08": 53655.4, "09": 31885.4, "10":  6478.4},
        18.0: {"01": 21419.3, "02":  5515.7, "03": 32125.4, "04":  6906.9, "05":  9948.7, "06":  9269.1, "07": 61065.7, "08": 54887.3, "09": 32326.3, "10":  6632.0},
        18.5: {"01": 21890.0, "02":  5624.7, "03": 32544.3, "04":  7065.8, "05": 10158.7, "06":  9387.1, "07": 62515.5, "08": 55587.3, "09": 32764.4, "10":  6785.1},
        19.0: {"01": 22361.4, "02":  5733.7, "03": 32962.5, "04":  7225.3, "05": 10368.0, "06":  9525.3, "07": 63963.9, "08": 55940.2, "09": 33255.0, "10":  6938.1},
        19.5: {"01": 22776.8, "02":  5830.6, "03": 33382.8, "04":  7384.4, "05": 10578.2, "06":  9707.7, "07": 65246.2, "08": 56291.6, "09": 33749.1, "10":  7092.0},
        20.0: {"01": 23200.7, "02":  5928.0, "03": 33802.4, "04":  7544.4, "05": 10601.0, "06":  9890.6, "07": 66527.7, "08": 56643.8, "09": 34237.6, "10":  7245.3},

        # ── 5c. Bulk weight — per-kg rates (INR/kg) ─────────────────────
        # Keys are range strings matching PDF; lookup uses _ups_bulk_key()
        "21-44":   {"01": 1088.4, "02":  284.4, "03": 1591.8, "04":  361.4, "05":  521.5, "06":  487.2, "07": 3171.6, "08": 2546.1, "09": 1540.7, "10":  347.2},
        "45-70":   {"01": 1018.8, "02":  241.5, "03": 1562.0, "04":  358.7, "05":  474.2, "06":  465.5, "07": 2801.7, "08": 2509.1, "09": 1474.0, "10":  344.4},
        "71-99":   {"01": 1018.8, "02":  199.5, "03": 1562.0, "04":  345.6, "05":  257.0, "06":  245.0, "07": 2801.7, "08": 2509.1, "09": 1474.0, "10":  265.4},
        "100-299": {"01":  989.7, "02":  186.2, "03": 1520.8, "04":  344.9, "05":  255.1, "06":  231.4, "07": 2700.1, "08": 2494.2, "09": 1432.1, "10":  265.2},
        "300-499": {"01":  989.7, "02":  881.1, "03": 1520.8, "04": 1632.3, "05": 1393.0, "06": 1642.9, "07": 2700.1, "08": 2494.2, "09": 1432.1, "10": 1569.1},
        "500-999": {"01":  989.7, "02":  881.1, "03": 1520.8, "04": 1632.3, "05": 1393.0, "06": 1642.9, "07": 2700.1, "08": 2494.2, "09": 1432.1, "10": 1569.1},
        "1000+":   {"01":  989.7, "02":  881.1, "03": 1520.8, "04": 1632.3, "05": 1393.0, "06": 1642.9, "07": 2700.1, "08": 2494.2, "09": 1432.1, "10": 1569.1},
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 2.  RATE LOOKUP HELPERS  (replaces DB queries in routes)
# ─────────────────────────────────────────────────────────────────────────────

def _round_to_half(weight: float) -> float:
    """Round weight UP to nearest 0.5 kg slab (FedEx & UPS rule)."""
    import math
    return math.ceil(weight * 2) / 2


def get_fedex_freight_rate(
    package_type: str,
    weight_kg: float,
    zone: str,
) -> float | None:
    """
    Look up FedEx base freight rate (INR).

    Args:
        package_type : "Envelope" | "Pak" | "Package"
        weight_kg    : chargeable weight (already rounded to 0.5 kg)
        zone         : single letter "A"–"L"

    Returns:
        float rate in INR, or None if not found.
    """
    table = STATIC_FEDEX_RATES.get(package_type)
    if not table:
        return None

    zone = zone.upper()

    # For Envelope, always use the 0.5 entry (flat rate)
    if package_type == "Envelope":
        row = table.get(0.5, {})
        return row.get(zone)

    # For Pak: max slab is 2.5 kg
    if package_type == "Pak" and weight_kg > 2.5:
        return None  # Pak not valid beyond 2.5 kg

    # Find exact slab
    slab = _round_to_half(weight_kg)

    # Clamp to max available slab
    slabs = sorted(k for k in table if isinstance(k, float))
    if slab > max(slabs):
        slab = max(slabs)

    row = table.get(slab)
    if row is None:
        return None
    return row.get(zone)


def get_fedex_zone(country: str) -> str | None:
    """Return FedEx zone code for a country name (case-insensitive)."""
    return STATIC_FEDEX_ZONE_MAP.get(country.strip().lower())


def _ups_bulk_key(weight_kg: float) -> str | None:
    """Map weight to UPS bulk range key string."""
    if 21 <= weight_kg <= 44:
        return "21-44"
    if 45 <= weight_kg <= 70:
        return "45-70"
    if 71 <= weight_kg <= 99:
        return "71-99"
    if 100 <= weight_kg <= 299:
        return "100-299"
    if 300 <= weight_kg <= 499:
        return "300-499"
    if 500 <= weight_kg <= 999:
        return "500-999"
    if weight_kg >= 1000:
        return "1000+"
    return None


def get_ups_freight_rate(
    package_type: str,
    weight_kg: float,
    zone_code: str,
) -> float | None:
    """
    Look up UPS Express Saver base freight rate (INR).

    For bulk weights (21+ kg) the rate table stores per-kg rates;
    this function returns the TOTAL charge (per_kg_rate × weight).

    Args:
        package_type : "LTR" | "Doc" | "NDC"
        weight_kg    : chargeable weight (already rounded to 0.5 kg)
        zone_code    : zero-padded string "01"–"10"

    Returns:
        float total rate in INR, or None if not found.
    """
    table = STATIC_UPS_RATES.get(package_type)
    if not table:
        return None

    # Normalise zone_code
    zone_code = zone_code.zfill(2)

    # Letter / Doc — flat rate regardless of weight beyond 0.5 kg
    if package_type in ("LTR", "Doc"):
        row = table.get(0.5, {})
        return row.get(zone_code)

    # NDC 0.5–20 kg exact slabs
    if weight_kg <= 20.0:
        slab = _round_to_half(weight_kg)
        row = table.get(slab)
        if row is None:
            return None
        return row.get(zone_code)

    # NDC bulk (21+ kg) — per-kg rate × weight
    bulk_key = _ups_bulk_key(weight_kg)
    if bulk_key is None:
        return None
    row = table.get(bulk_key)
    if row is None:
        return None
    per_kg = row.get(zone_code)
    if per_kg is None:
        return None
    return round(per_kg * weight_kg, 2)


def get_ups_zone(country: str, service_type: str = "Express Saver") -> str | None:
    """
    Return UPS zone code string (e.g. "05") for a country (case-insensitive).
    service_type is accepted for API compatibility but only Express Saver
    zones are stored in static data.
    """
    return STATIC_UPS_ZONE_MAP.get(country.strip().lower())


# ─────────────────────────────────────────────────────────────────────────────
# 3.  SESSION-SCOPED OVERRIDE STORE
# ─────────────────────────────────────────────────────────────────────────────

_overrides: dict[str, dict] = {}
_lock = threading.Lock()


def override_charges(session_id: str, patches: dict) -> None:
    """
    Merge `patches` into the session override store for `session_id`.

    Example:
        override_charges("sess-abc", {
            "clearance": {
                "FEDEX": {"LTL": {"advancement_charge": "900.00"}}
            },
            "bank": {"commission_charges": 600},
            "other": {"FEDEX": {"fuel_surcharge_percentage": 0.34}},
            "local": {"dtdc": {"safe_express": {"Metros": {"upto_3kg": 110}}}},
        })
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

    Keys:
        clearance       → STATIC_CLEARANCE_CHARGES
        other           → STATIC_OTHER_CHARGES
        bank            → STATIC_BANK_CHARGES
        local           → STATIC_LOCAL_FREIGHT
        fedex_zone_map  → STATIC_FEDEX_ZONE_MAP   (read-only reference)
        ups_zone_map    → STATIC_UPS_ZONE_MAP      (read-only reference)
    """
    base = {
        "clearance":      copy.deepcopy(STATIC_CLEARANCE_CHARGES),
        "other":          copy.deepcopy(STATIC_OTHER_CHARGES),
        "bank":           copy.deepcopy(STATIC_BANK_CHARGES),
        "local":          copy.deepcopy(STATIC_LOCAL_FREIGHT),
        "fedex_zone_map": STATIC_FEDEX_ZONE_MAP,   # read-only; no deepcopy needed
        "ups_zone_map":   STATIC_UPS_ZONE_MAP,
    }

    if session_id:
        with _lock:
            patches = _overrides.get(session_id, {})
        if patches:
            base = _deep_merge(base, patches)

    return base


# ─────────────────────────────────────────────────────────────────────────────
# 4.  INTERNAL HELPERS
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