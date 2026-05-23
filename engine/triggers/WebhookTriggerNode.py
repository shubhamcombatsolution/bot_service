import logging
from typing import Dict, Any, List
from engine.nodes.base import BaseNode

logger = setup_logging("WebhookTriggerNode", level="DEBUG")


class WebhookTriggerNode(BaseNode):
    """
    Generic Webhook Trigger Node
    
    🔹 Receives external events via HTTP POST
    🔹 No polling or fetching - purely event-driven
    🔹 Supports any webhook payload structure
    🔹 Works like GmailTriggerNode but for webhooks
    """
    
    is_trigger_node = True
    node_type = "WebhookTriggerNode"

    def __init__(self, node_id: str, config: Dict[str, Any]):
        super().__init__(node_id, config)
        
        # Webhook-specific configuration
        self.webhook_name = config.get("webhook_name", "default_webhook")
        self.event_filter = config.get("event_filter", {})  # Optional filtering
        self.field_mapping = config.get("field_mapping", {})  # Optional field mapping
        
        logger.info(f"[WEBHOOK_TRIGGER] Initialized webhook trigger: {self.webhook_name}")

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute webhook trigger node.
        
        Expects prefetched_events in trigger_data (injected by webhook endpoint).
        Returns the webhook event payload to downstream nodes.
        """
        try:
            # Get trigger data (injected by webhook endpoint)
            trigger_data = context.get("trigger_data", {})
            node_trigger_data = trigger_data.get(self.node_id, {})
            
            # Extract prefetched events
            prefetched_events = node_trigger_data.get("prefetched_events", [])
            
            if not prefetched_events:
                logger.warning(f"[WEBHOOK_TRIGGER] No prefetched events found for node {self.node_id}")
                return {
                    "status": "success",
                    "events": [],
                    "message": "No webhook events received"
                }
            
            logger.info(f"[WEBHOOK_TRIGGER] Processing {len(prefetched_events)} webhook event(s)")
            
            # Process events (apply optional filtering/mapping)
            processed_events = []
            for event in prefetched_events:
                processed_event = self._process_event(event)
                if processed_event:
                    processed_events.append(processed_event)
            
            logger.info(f"[WEBHOOK_TRIGGER] Successfully processed {len(processed_events)} event(s)")
            
            return {
                "status": "success",
                "events": processed_events,
                "webhook_name": self.webhook_name,
                "event_count": len(processed_events)
            }
            
        except Exception as e:
            logger.exception(f"[WEBHOOK_TRIGGER] Error processing webhook events: {e}")
            return {
                "status": "error",
                "error": str(e),
                "events": []
            }

    def _process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process individual webhook event.
        Apply optional filtering and field mapping.
        """
        try:
            # Apply event filter if configured
            if self.event_filter:
                if not self._matches_filter(event, self.event_filter):
                    logger.debug(f"[WEBHOOK_TRIGGER] Event filtered out: {event.get('event')}")
                    return None
            
            # Apply field mapping if configured
            if self.field_mapping:
                event = self._apply_field_mapping(event, self.field_mapping)
            
            return event
            
        except Exception as e:
            logger.error(f"[WEBHOOK_TRIGGER] Error processing event: {e}")
            return None

    def _matches_filter(self, event: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """
        Check if event matches configured filters.
        Example filter: {"event": "supplier.selected", "status": "active"}
        """
        for key, expected_value in filters.items():
            event_value = event.get(key)
            if event_value != expected_value:
                return False
        return True

    def _apply_field_mapping(self, event: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Apply field mapping to event.
        Example mapping: {"supplier_email": "email", "supplier_id": "id"}
        """
        mapped_event = event.copy()
        for source_field, target_field in mapping.items():
            if source_field in event:
                mapped_event[target_field] = event[source_field]
        return mapped_event

    def validate(self) -> bool:
        """Validate webhook trigger configuration."""
        if not self.webhook_name:
            logger.error("[WEBHOOK_TRIGGER] webhook_name is required")
            return False
        return True