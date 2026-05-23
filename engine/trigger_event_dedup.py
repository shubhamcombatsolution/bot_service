from app.models.processed_trigger_event import ProcessedTriggerEvent
from sqlalchemy.exc import IntegrityError
from app.models.processed_trigger_event import ProcessedTriggerEvent

def is_event_already_processed(
    session,
    tenant_id: int,
    trigger_id: int,
    event_id: str,
) -> bool:
    """
    Returns True if this trigger already processed this event.
    """
    return (
        session.query(ProcessedTriggerEvent.id)
        .filter(
            ProcessedTriggerEvent.tenant_id == tenant_id,
            ProcessedTriggerEvent.trigger_id == trigger_id,
            ProcessedTriggerEvent.event_id == event_id,
        )
        .first()
        is not None
    )




def mark_event_as_processed(
    session,
    tenant_id: int,
    trigger_id: int,
    event_id: str,
    event_source: str,
):
    """
    Idempotent insert.
    Safe if called multiple times.
    """
    try:
        session.add(
            ProcessedTriggerEvent(
                tenant_id=tenant_id,
                trigger_id=trigger_id,
                event_id=event_id,
                event_source=event_source,
            )
        )
        session.flush()   # ❗ do NOT commit here
    except IntegrityError:
        session.rollback()  # already exists → safe to ignore
