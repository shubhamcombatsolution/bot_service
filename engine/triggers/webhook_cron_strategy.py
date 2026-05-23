import logging
from datetime import datetime
from typing import Dict, Any, List

from engine.triggers.base_strategy import BaseTriggerStrategy

logger = logging.getLogger("WebhookCronStrategy")
logger.setLevel(logging.DEBUG)


class WebhookCronStrategy(BaseTriggerStrategy):
    """
    Webhook trigger strategy for event-based workflows.
    🔹 Webhook triggers are event-based, NOT scheduled
    🔹 They don't run on cron - they run when events are received
    🔹 This strategy exists for consistency but should_run always returns False
    """
    
    trigger_type = "webhook"

    def should_run(self, now: datetime) -> bool:
        """
        Webhook triggers are event-based and never run on schedule.
        They only execute when an external system calls the webhook endpoint.
        """
        logger.debug("[WEBHOOK_CRON] Webhook triggers are event-based → cron skip.")
        return False
    
    def fetch_events(self, db_session) -> List[Dict[str, Any]]:
        """
        Webhook triggers don't fetch events - they receive them via HTTP POST.
        This method exists for interface consistency but won't be called.
        """
        logger.debug("[WEBHOOK_CRON] Webhook triggers don't fetch events - they receive via HTTP.")
        return []