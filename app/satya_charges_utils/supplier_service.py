# services/supplier_service.py
from typing import List
from app.models import SupplierQuotation, SupplierQuotationLineItem
from logging_config import setup_logging

logger = setup_logging(
    name="supplier_service",
    level="DEBUG",
    group="charges"
)



def get_suppliers(sys_rfq_id: str) -> List[SupplierQuotation]:
    return SupplierQuotation.query.filter_by(
        sys_rfq_id=sys_rfq_id
    ).all()


def get_supplier_items(supplier_quotation_id: str) -> List[SupplierQuotationLineItem]:
    return SupplierQuotationLineItem.query.filter_by(
        supplier_quotation_id=supplier_quotation_id
    ).all()
