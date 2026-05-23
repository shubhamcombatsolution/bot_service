# services/rfq_service.py
from typing import List
from app.models import RfqHeader, RfqLineItems
from logging_config import setup_logging

logger = setup_logging(
    name="rfq_service",
    level="DEBUG",
    group="charges"
)




def get_rfq(sys_rfq_id: str) -> RfqHeader:
    rfq = RfqHeader.query.filter_by(
        sys_rfq_id=sys_rfq_id,
        deleted_flag=False
    ).first()

    if not rfq:
        raise ValueError("RFQ not found")

    logger.info(f"RFQ loaded: {sys_rfq_id}")
    return rfq


def get_rfq_items(sys_rfq_id: str) -> List[RfqLineItems]:
    return RfqLineItems.query.filter_by(
        sys_rfq_id=sys_rfq_id,
        deleted_flag=False
    ).all()
