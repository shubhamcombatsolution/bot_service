"""
static_charges_adapter.py
==========================
Adapter functions that convert static_charges.py data structures
into the formats expected by the existing builder functions.

This bridges the gap between static dict data and the ORM-style usage.
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def fmt(val) -> str:
    """Format value to 2 decimal places or return None"""
    return f"{float(val):.2f}" if val is not None else None


def build_bank_charges_from_static(
    static_bank_data: Dict[str, Any],
    supplier_exchange_rate: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Convert static bank charges dict to builder format.
    
    Static format:
        {
            "DBS_percentage": 0.0025,
            "commission_charges": 500.0,
            "cable_charges": 500.0,
        }
    
    Output format (legacy):
        [{
            "DBS_percentage": "0.0025",
            "commission_charges": "500.00",
            "cable_charges": "500.00",
        }]
    """
    if not static_bank_data:
        return []
    
    result = {
        "DBS_percentage": None,
        "commission_charges": None,
        "cable_charges": None,
    }
    
    # Extract from static data
    if "DBS_percentage" in static_bank_data:
        result["DBS_percentage"] = static_bank_data["DBS_percentage"]
    
    if "commission_charges" in static_bank_data:
        result["commission_charges"] = static_bank_data["commission_charges"]
    
    if "cable_charges" in static_bank_data:
        result["cable_charges"] = static_bank_data["cable_charges"]
    
    # Format output (only non-null values)
    formatted = {
        k: fmt(v) if isinstance(v, (int, float)) else v
        for k, v in result.items()
        if v is not None
    }
    
    return [formatted] if formatted else []


def build_clearance_charges_from_static(
    static_clearance_data: Dict[str, Dict[str, Dict[str, Any]]]
) -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    Convert static clearance charges to builder format.
    
    Static format (from STATIC_CLEARANCE_CHARGES):
        {
            "FEDEX": {
                "LTL": {
                    "duties_tax_percentage": "0.02",
                    "advancement_charge": "800.00",
                    ...
                },
                "GTL": { ... }
            },
            "UPS": { ... },
            "FF": { ... }
        }
    
    Output format (legacy):
        same as input (already in correct format)
    """
    if not static_clearance_data:
        logger.warning("No clearance charges data found")
        return {}
    
    # Static data is already in the correct format
    # Just format numeric values as strings
    result = {}
    
    for carrier, shipment_types in static_clearance_data.items():
        result[carrier] = {}
        
        for shipment, charges in shipment_types.items():
            result[carrier][shipment] = {}
            
            for charge_name, amount in charges.items():
                # Format numeric values
                if isinstance(amount, (int, float)):
                    result[carrier][shipment][charge_name] = fmt(amount)
                else:
                    result[carrier][shipment][charge_name] = amount
    
    return result


def build_local_freight_charges_from_static(
    static_local_data: Dict[str, Any],
    delivery_category: str
) -> List[Dict[str, Any]]:
    """
    Convert static local freight charges to builder format for a specific category.
    
    Static format (from STATIC_LOCAL_FREIGHT):
        {
            "dtdc": {
                "volumetric_divisor": 4750,
                "priority": {
                    "Within City": {"upto_half_kg": 25, ...},
                    ...
                },
                "safe_express": { ... }
            },
            "bluedart": { ... }
        }
    
    Output format (list of tariff objects per carrier/service):
        [{
            "local_delivery_partner": "dtdc",
            "shipment_type": "priority",
            "delivery_category": "Within City",
            "upto_half_kg": 25,
            ...
        }]
    """
    if not static_local_data:
        logger.warning("No local freight charges data")
        return []
    
    result = []

    # Normalize the requested category so matching is case- and
    # separator-insensitive (e.g. "Rest of India", "rest_of_india" and
    # "Rest of india" all map to the same static key).
    def _norm(s: str) -> str:
        return str(s).replace("_", " ").strip().lower()

    requested_norm = _norm(delivery_category)

    for carrier, carrier_data in static_local_data.items():
        if carrier == "volumetric_divisor":
            continue  # Skip metadata

        if not isinstance(carrier_data, dict):
            continue

        # ----------------------------------------------------------------
        # BlueDart / flat-scalar carrier detection
        # BlueDart stores scalars (freight_min, freight_percentage, etc.)
        # at the carrier level rather than inside category sub-dicts.
        # Detect this by checking for the required scalar fields.
        # ----------------------------------------------------------------
        if isinstance(carrier_data.get("freight_min"), (int, float)) and \
                isinstance(carrier_data.get("freight_percentage"), (int, float)):
            # Flat-scalar carrier (BlueDart): emit one tariff row per request.
            # zone_multiplier is a nested origin_zone→dest_zone matrix;
            # callers can pass zone_multiplier explicitly. Default to 1.0.
            tariff = {
                "local_delivery_partner": carrier.lower(),
                "shipment_type": "express",
                "delivery_category": delivery_category,
            }
            # Copy all direct scalar fields (skip nested dicts like
            # zone_multiplier / state_zone_map / volumetric_divisor).
            _SKIP = {"zone_multiplier", "state_zone_map", "volumetric_divisor"}
            for k, v in carrier_data.items():
                if k in _SKIP:
                    continue
                if isinstance(v, (int, float)):
                    tariff[k] = float(v)
            result.append(tariff)
            continue  # Don't descend into nested service/category loop

        # ----------------------------------------------------------------
        # Normal nested structure (DTDC-style):
        #   carrier_data = { service_type: { category: { slabs } } }
        # ----------------------------------------------------------------
        for service_type, categories_data in carrier_data.items():
            if service_type == "volumetric_divisor":
                continue

            if not isinstance(categories_data, dict):
                continue

            # Match the requested category against the actual static keys
            # using normalized comparison.
            matched_key = next(
                (k for k in categories_data if _norm(k) == requested_norm),
                None
            )

            if matched_key is not None:
                sanitized_category = matched_key
                category_charges = categories_data[matched_key]

                # category_charges must be a dict (skip multiplier/zone rows)
                if not isinstance(category_charges, dict):
                    continue

                # Build tariff object
                tariff = {
                    "local_delivery_partner": carrier.lower(),
                    "shipment_type": service_type.lower(),
                    "delivery_category": sanitized_category.lower(),
                }

                # Add the category-specific rates
                for charge_name, amount in category_charges.items():
                    if charge_name not in ["local_delivery_partner", "shipment_type", "delivery_category"]:
                        if isinstance(amount, (int, float)):
                            tariff[charge_name] = float(amount)
                        else:
                            tariff[charge_name] = amount

                # Also include service-level surcharge siblings (fuel %, risk %,
                # risk min, etc.) which live next to the category dicts, not
                # inside them. Without these the DTDC fuel/risk surcharges would
                # be lost from the returned tariff.
                for sib_name, sib_val in categories_data.items():
                    if isinstance(sib_val, dict):
                        continue  # other category dicts
                    if sib_name in tariff:
                        continue
                    if isinstance(sib_val, (int, float)):
                        tariff[sib_name] = float(sib_val)
                    else:
                        tariff[sib_name] = sib_val

                result.append(tariff)

    return result


def build_other_charges_from_static(
    static_other_data: Dict[str, Any],
    carrier: str
) -> List[Dict[str, Any]]:
    """
    Convert static other charges (fuel, ADG, oversize, surge) to builder format.
    
    Static format (from STATIC_OTHER_CHARGES):
        {
            "FEDEX": {
                "fuel_surcharge_percentage": 0.335,
                "oversize_threshold_cm": 120,
                "oversize_charge_inr": 20500,
            },
            "UPS": { ... },
            "COMMON": { ... }
        }
    
    Output format (list of charge objects):
        [{
            "carrier": "FEDEX",
            "charge_category": "fuel_surcharge",
            "charge_name": "Fuel Surcharge",
            "amount": "0.335",
            "amount_type": "percentage",
        }, ...]
    """
    if not static_other_data:
        return []
    
    result = []
    carrier_upper = carrier.upper()
    
    if carrier_upper not in static_other_data:
        logger.debug(f"No other charges found for carrier: {carrier_upper}")
        return result
    
    carrier_charges = static_other_data[carrier_upper]
    
    # Convert static format to ORM-like format
    for charge_name, amount in carrier_charges.items():
        if charge_name == "fuel_surcharge_percentage":
            result.append({
                "carrier": carrier_upper,
                "charge_category": "fuel_surcharge",
                "charge_name": "Fuel Surcharge",
                "amount": amount,
                "amount_type": "percentage",
                "condition_value": None,
            })
        
        elif charge_name == "oversize_threshold_cm":
            # Note: threshold is metadata, actual charge is separate
            pass
        
        elif charge_name == "oversize_charge_inr":
            result.append({
                "carrier": carrier_upper,
                "charge_category": "oversize",
                "charge_name": "Oversize Charge",
                "amount": amount,
                "amount_type": "fixed",
                "condition_value": f"> {carrier_charges.get('oversize_threshold_cm', 120)} cm",
            })
        
        elif charge_name == "accessible_dangerous_goods_charge_min":
            result.append({
                "carrier": carrier_upper,
                "charge_category": "dangerous_goods",
                "charge_name": "ADG - Min Charge",
                "amount": amount,
                "amount_type": "fixed",
                "condition_value": None,
            })
        
        elif charge_name == "accessible_dangerous_goods_charge_per_kg":
            result.append({
                "carrier": carrier_upper,
                "charge_category": "dangerous_goods",
                "charge_name": "ADG - Per KG",
                "amount": amount,
                "amount_type": "per_kg",
                "condition_value": None,
            })
        
        elif "surge_fees" in charge_name and isinstance(amount, dict):
            # UPS surge fees
            for destination, surge_amount in amount.items():
                result.append({
                    "carrier": carrier_upper,
                    "charge_category": "surge_fee",
                    "charge_name": f"Surge Fee - {destination}",
                    "amount": surge_amount,
                    "amount_type": "fixed",
                    "condition_value": f"India → {destination}",
                })
    
    return result


def get_fedex_zone_from_static(
    static_zone_map: Dict[str, str],
    origin_country: str
) -> Optional[str]:
    """
    Get FedEx zone code for origin country from static zone map.
    
    Static format:
        {
            "united arab emirates": "A",
            "pakistan": "B",
            ...
        }
    """
    if not origin_country:
        return None
    
    origin_lower = origin_country.lower().strip()
    zone = static_zone_map.get(origin_lower)
    
    if not zone:
        logger.warning(f"Unknown FedEx zone for country: {origin_country}")
    
    return zone


def get_ups_zone_from_static(
    static_zone_map: Dict[str, int],
    destination_country: str
) -> Optional[int]:
    """
    Get UPS zone code for destination country from static zone map.
    """
    if not destination_country:
        return None
    
    destination_lower = destination_country.lower().strip()
    zone = static_zone_map.get(destination_lower)
    
    if not zone:
        logger.warning(f"Unknown UPS zone for country: {destination_country}")
    
    return zone


def apply_charge_overrides(
    base_charges: Dict[str, Any],
    overrides: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Deep merge charge overrides into base charges.
    Overrides are applied at request level for agent modifications.
    """
    import copy
    
    result = copy.deepcopy(base_charges)
    
    def merge_dict(base, patch):
        for k, v in patch.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                base[k] = merge_dict(base[k], v)
            else:
                base[k] = copy.deepcopy(v)
        return base
    
    return merge_dict(result, overrides)


def calculate_bank_charges_amount(
    bank_charges_dict: Dict[str, Any],
    invoice_amount: float,
    invoice_currency: str = "USD"
) -> Dict[str, float]:
    """
    Calculate actual bank charge amounts from percentages and fixed charges.
    
    Returns:
        {
            "DBS_charge": float,
            "commission_charge": float,
            "cable_charge": float,
            "total_bank_charges": float
        }
    """
    result = {
        "DBS_charge": 0.0,
        "commission_charge": 0.0,
        "cable_charge": 0.0,
    }
    
    # DBS percentage charge
    if "DBS_percentage" in bank_charges_dict:
        dbs_pct = bank_charges_dict["DBS_percentage"]
        if isinstance(dbs_pct, str):
            dbs_pct = float(dbs_pct)
        result["DBS_charge"] = invoice_amount * dbs_pct
    
    # Commission (fixed)
    if "commission_charges" in bank_charges_dict:
        comm = bank_charges_dict["commission_charges"]
        if isinstance(comm, str):
            comm = float(comm)
        result["commission_charge"] = comm
    
    # Cable charges (fixed)
    if "cable_charges" in bank_charges_dict:
        cable = bank_charges_dict["cable_charges"]
        if isinstance(cable, str):
            cable = float(cable)
        result["cable_charge"] = cable
    
    result["total_bank_charges"] = (
        result["DBS_charge"] +
        result["commission_charge"] +
        result["cable_charge"]
    )
    
    return result


def calculate_clearance_charges_amount(
    clearance_dict: Dict[str, Any],
    carrier: str,
    shipment_type: str,
    invoice_amount: float,
    weight_kg: float = 0.0
) -> Dict[str, float]:
    """
    Calculate actual clearance charge amounts from rules.
    
    Applies:
    - Duty percentage on invoice value
    - Fixed charges (advancement, BOE, TSP, etc.)
    - Per-KG charges (if applicable)
    """
    result = {}
    
    carrier_upper = carrier.upper()
    
    if carrier_upper not in clearance_dict:
        logger.warning(f"No clearance charges for carrier: {carrier}")
        return result
    
    if shipment_type not in clearance_dict[carrier_upper]:
        logger.warning(f"No clearance charges for {carrier_upper}/{shipment_type}")
        return result
    
    charges = clearance_dict[carrier_upper][shipment_type]
    
    for charge_name, amount in charges.items():
        if amount is None:
            continue
        
        if isinstance(amount, str):
            amount = float(amount)
        
        if "percentage" in charge_name.lower():
            # Calculate as percentage of invoice
            calculated = invoice_amount * amount
            result[charge_name] = calculated
        elif "per_kg" in charge_name.lower():
            # Calculate per kilogram
            calculated = weight_kg * amount
            result[charge_name] = calculated
        else:
            # Fixed charge
            result[charge_name] = amount
    
    result["total_clearance"] = sum(v for v in result.values() if isinstance(v, (int, float)))
    
    return result


def calculate_local_freight_amount(
    tariff: Dict[str, Any],
    weight_kg: float,
    invoice_value: float = 0.0,
    zone_multiplier: float = 1.0
) -> float:
    """
    Calculate local freight charge based on weight slabs and rates.
    
    DTDC Example:
        upto_half_kg: 25 (for 0-500g)
        additional_per_half_kg: 15 (for each 500g block above 500g)
        per_kg_after_10_kg: 26 (for kg > 10kg)
        fuel_surcharge_percentage: 0.10
        risk_on_value_percentage_*: 0.001
    
    Returns: Total freight charge (INR)
    """
    base_charge = 0.0
    surcharges = 0.0
    
    service_type = tariff.get("shipment_type", "").lower()
    carrier = tariff.get("local_delivery_partner", "").lower()
    
    # ============ DTDC PRIORITY ============
    if service_type == "priority":
        if weight_kg <= 0.5:
            base_charge = tariff.get("upto_half_kg", 0)
        elif weight_kg <= 10:
            # 500g base + additional 500g blocks
            base_charge = tariff.get("upto_half_kg", 0)
            additional_kg = weight_kg - 0.5
            additional_blocks = (additional_kg + 0.49999) // 0.5  # round up
            base_charge += additional_blocks * tariff.get("additional_per_half_kg", 0)
        else:
            # > 10kg: cap the 0.5kg-block portion at 10kg (= base + 19 blocks),
            # then charge per-kg for the weight above 10kg (doc 5.2).
            base_charge = tariff.get("upto_half_kg", 0)
            base_charge += 19 * tariff.get("additional_per_half_kg", 0)
            excess_kg = weight_kg - 10
            base_charge += excess_kg * tariff.get("per_kg_after_10_kg", 0)
        
        # Risk charge (percentage of invoice value)
        if "risk_on_value_percentage_priority" in tariff:
            risk_pct = tariff["risk_on_value_percentage_priority"]
            if isinstance(risk_pct, str):
                risk_pct = float(risk_pct)
            risk_amount = invoice_value * risk_pct
            risk_min = tariff.get("risk_surcharge_min", 0)
            surcharges += max(risk_amount, risk_min)
    
    # ============ DTDC SAFE EXPRESS ============
    elif service_type == "safe_express":
        if weight_kg <= 3:
            base_charge = tariff.get("upto_3kg", 0)
        else:
            base_charge = tariff.get("upto_3kg", 0)
            excess_kg = weight_kg - 3
            base_charge += excess_kg * tariff.get("per_kg_after_3_kg", 0)
        
        # Risk charge
        if "risk_on_value_percentage_safe_express" in tariff:
            risk_pct = tariff["risk_on_value_percentage_safe_express"]
            if isinstance(risk_pct, str):
                risk_pct = float(risk_pct)
            risk_amount = invoice_value * risk_pct
            risk_min = tariff.get("risk_surcharge_min", 0)
            surcharges += max(risk_amount, risk_min)
    
    # ============ BLUEDART ============
    elif carrier == "bluedart":
        # Doc 5.1: full pipeline with zone multiplier, CAF on (base+fuel),
        # fixed non-doc + risk charges, then GST.
        freight_min = (
            tariff.get("bluedart_freight_min")
            or tariff.get("freight_min")
            or 150
        )
        freight_pct = (
            tariff.get("bluedart_freight_percentage")
            or tariff.get("freight_percentage")
            or 0.15
        )

        def _f(key, default):
            v = tariff.get(key, default)
            return float(v) if isinstance(v, str) else v

        base = max(freight_min, zone_multiplier * freight_pct * invoice_value)
        fuel = base * _f("fuel_surcharge_percentage", 0.36)
        sub1 = base + fuel
        caf = sub1 * _f("currency_adjustment_factor_percentage", 0.15)
        sub2 = sub1 + caf
        sub3 = sub2 + _f("non_document_charge", 50) + _f("risk_charge", 100)
        gst = sub3 * _f("gst_percentage", 0.18)
        return round(sub3 + gst, 2)

    # ============ APPLY SURCHARGES (DTDC) ============
    # Fuel surcharge (percentage on base freight)
    fuel_pct = tariff.get("fuel_surcharge_percentage") or tariff.get("dtdc_fuel_surcharge_percentage")
    if fuel_pct:
        if isinstance(fuel_pct, str):
            fuel_pct = float(fuel_pct)
        surcharges += base_charge * fuel_pct
    
    # CAF (Currency Adjustment Factor) - BlueArt
    caf_pct = tariff.get("currency_adjustment_factor_percentage")
    if caf_pct:
        if isinstance(caf_pct, str):
            caf_pct = float(caf_pct)
        surcharges += base_charge * caf_pct
    
    total = base_charge + surcharges
    
    return round(total, 2)
