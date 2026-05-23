# satya_charges_utils/derive_service.py

from typing import Iterable
from app.satya_charges_utils.pincode_classifier import classify_pincode_location
from logging_config import setup_logging

logger = setup_logging(
    name="derive_service",
    level="DEBUG",
    group="charges"
)


# -------------------------------------------------------------------
# Derive total shipment weight
# -------------------------------------------------------------------
def derive_total_shipment_weight(
    supplier_items: Iterable
) -> float:
    """
    Extracts numeric values from weight_of_package
    and returns total shipment weight in KG.
    """

    total_weight = 0.0

    for item in supplier_items:
        raw_weight = item.weight_of_package
        if not raw_weight:
            continue

        try:
            numeric = "".join(
                ch for ch in raw_weight if ch.isdigit() or ch == "."
            )
            weight = float(numeric)
            total_weight += weight

        except Exception:
            logger.warning(
                f"Invalid weight format: {raw_weight}",
                extra={"supplier_line_item": item.supplier_line_item_id},
            )

    logger.info(f"Derived total shipment weight: {total_weight} kg")
    return total_weight


# -------------------------------------------------------------------
# Derive delivery category from RFQ
# -------------------------------------------------------------------
def derive_delivery_category(
    rfq,
    current_city: str = "bangalore",
    current_state: str = "karnataka",
) -> str:
    """
    Uses pincode classifier to derive delivery category.
    """

    if not rfq.delivery_pincode:
        logger.warning("RFQ has no delivery pincode")
        return "unknown"

    category = classify_pincode_location(
        pincode=rfq.delivery_pincode,
        current_city=current_city,
        current_state=current_state,
    )

    logger.info(
        f"Derived delivery category={category} "
        f"for pincode={rfq.delivery_pincode}"
    )

    return category
