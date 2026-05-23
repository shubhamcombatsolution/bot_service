# services/charge_service.py
from app.models.charges_models import (
    BankCharge,
    ClearanceCharges,
    LocalFreightCharge,
    FedexFreightCharge,
    FedexOriginZoneConfig,
    UPSOriginZoneConfig,
    OtherCharge,
)
from sqlalchemy import func, and_

from logging_config import setup_logging

logger = setup_logging(
    name="charge_service",
    level="DEBUG",
    group="charges"
)


def get_bank_charges():
    """Get all active bank charges"""
    return BankCharge.query.filter_by(
        del_flg=False
    ).all()


def get_clearance_charges(carrier: str):
    """Get clearance charges for a specific carrier"""
    return ClearanceCharges.query.filter_by(
        carrier=carrier,
        del_flg=False
    ).all()


def get_local_charges(carrier: str, category: str):
    """Get local freight charges for carrier and route category"""
    return LocalFreightCharge.query.filter(
        func.lower(LocalFreightCharge.route_type) == category.lower(),
        func.lower(LocalFreightCharge.carrier).contains(carrier.lower()),
        LocalFreightCharge.del_flg == False
    ).all()

def get_all_local_charges_by_category(category: str):
    return LocalFreightCharge.query.filter(
        LocalFreightCharge.del_flg == False,
        func.lower(LocalFreightCharge.route_type).in_([
            category.lower(),
            "all routes"
        ])
    ).all()



def get_other_charges(carrier: str):
    """
    Get other charges (fuel surcharge, oversize, dangerous goods, etc.) 
    for a specific carrier from tbl_other_charges
    """
    return OtherCharge.query.filter(
        func.lower(OtherCharge.carrier) == carrier.lower(),
        OtherCharge.del_flg == False
    ).all()


def get_zone(carrier: str, country: str):
    """Get zone configuration for carrier and country"""
    if not carrier or not country:
        return None
        
    if carrier.lower() == "fedex":
        return FedexOriginZoneConfig.query.filter_by(
            origin_country=country,
            del_flg=False
        ).first()

    if carrier.lower() == "ups":
        return UPSOriginZoneConfig.query.filter_by(
            destination_country=country,
            del_flg=False
        ).first()

    return None


def calculate_fedex_freight_charge(
    origin_country: str,
    total_weight: float,
    package_type: str = "parcel"
) -> dict | None:
    """
    Calculate FedEx freight charge based on origin country, 
    total weight, and package type
    """
    logger.info(
        "FedEx freight calculation | country=%s | weight=%s | package=%s",
        origin_country, total_weight, package_type
    )

    # Get zone configuration for origin country
    zone_cfg = FedexOriginZoneConfig.query.filter_by(
        origin_country=origin_country,
        del_flg=False
    ).first()

    if not zone_cfg:
        logger.warning("No FedEx zone config for country: %s", origin_country)
        return None

    # Build zone field name (e.g., "zone_A", "zone_B")
    zone_field = f"zone_{zone_cfg.zone_code.upper()}"

    # Find the appropriate weight slab
    # Get the first slab where weight_kg >= total_weight
    slab = FedexFreightCharge.query.filter(
        and_(
            FedexFreightCharge.package_type == package_type,
            FedexFreightCharge.weight_kg >= total_weight,
            FedexFreightCharge.del_flg == False
        )
    ).order_by(FedexFreightCharge.weight_kg.asc()).first()

    if not slab:
        logger.warning(
            "No FedEx freight slab found for weight=%s, package=%s",
            total_weight, package_type
        )
        return None

    # Check if zone field exists on the slab
    if not hasattr(slab, zone_field):
        logger.error("Zone field '%s' does not exist on slab", zone_field)
        return None

    # Get the amount for the zone
    amount = getattr(slab, zone_field)
    if amount is None:
        logger.warning(
            "No rate defined for zone=%s in slab weight=%s",
            zone_field, slab.weight_kg
        )
        return None

    logger.info(
        "FedEx freight calculated | zone=%s | weight_slab=%s | amount=%s",
        zone_cfg.zone_code, slab.weight_kg, amount
    )

    return {
        "carrier": "FEDEX",
        "package_type": package_type,
        "weight_slab": float(slab.weight_kg),
        "zone": zone_cfg.zone_code.upper(),
        "amount": float(amount),
    }


def calculate_ups_freight_charge(
    destination_country: str,
    total_weight: float,
    service_type: str = "Express",
    shipment_direction: str = "Export",
    package_type: str = "Package"
) -> dict | None:
    """
    Calculate UPS freight charge based on destination country,
    weight, service type, and shipment direction
    """
    logger.info(
        "UPS freight calculation | country=%s | weight=%s | service=%s",
        destination_country, total_weight, service_type
    )

    # Get zone configuration
    zone_cfg = UPSOriginZoneConfig.query.filter_by(
        destination_country=destination_country,
        shipment_direction=shipment_direction,
        service_type=service_type,
        del_flg=False
    ).first()

    if not zone_cfg:
        logger.warning(
            "No UPS zone config for country=%s, direction=%s, service=%s",
            destination_country, shipment_direction, service_type
        )
        return None

    # Build zone field name (e.g., "zone_01", "zone_02")
    zone_field = f"zone_{zone_cfg.zone_code}"

    # Find appropriate weight slab
    # Weight slabs might be like "0.5", "1.0", "2.0", etc.
    from app.models.charges_models import UPSFreightCharge
    
    slab = UPSFreightCharge.query.filter(
        and_(
            UPSFreightCharge.service_type == service_type,
            UPSFreightCharge.shipment_direction == shipment_direction,
            UPSFreightCharge.package_type == package_type,
            UPSFreightCharge.del_flg == False
        )
    ).all()

    if not slab:
        logger.warning("No UPS freight slabs found for given criteria")
        return None

    # Find the right slab based on weight
    selected_slab = None
    for s in slab:
        try:
            slab_weight = float(s.weight_slab)
            if slab_weight >= total_weight:
                if not selected_slab or slab_weight < float(selected_slab.weight_slab):
                    selected_slab = s
        except ValueError:
            continue

    if not selected_slab:
        logger.warning("No suitable UPS weight slab found for weight=%s", total_weight)
        return None

    # Get amount for the zone
    if not hasattr(selected_slab, zone_field):
        logger.error("Zone field '%s' does not exist", zone_field)
        return None

    amount = getattr(selected_slab, zone_field)
    if amount is None:
        logger.warning("No rate for zone=%s", zone_field)
        return None

    logger.info(
        "UPS freight calculated | zone=%s | weight_slab=%s | amount=%s",
        zone_cfg.zone_code, selected_slab.weight_slab, amount
    )

    return {
        "carrier": "UPS",
        "service_type": service_type,
        "package_type": package_type,
        "weight_slab": selected_slab.weight_slab,
        "zone": zone_cfg.zone_code,
        "amount": float(amount),
    }