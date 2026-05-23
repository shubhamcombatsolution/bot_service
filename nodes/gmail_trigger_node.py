# nodes/gmail_trigger_node.py

from datetime import datetime
from engine.base_node import BaseNode
from engine.registry import register_node
from engine.services.gmail_service import GmailService
from logging_config import setup_logging


logger = setup_logging(__name__, level="DEBUG")




@register_node("GmailTriggerNode")
class GmailTriggerNode(BaseNode):
    is_trigger_node = True  
    """Supports Manual + TriggerService Execution (AUTO mode)"""

    def execute(self, inputs):
        logger.info("📩 Executing GmailTriggerNode")

        # ----------------------------
        # 1️⃣ Tenant ID Check
        # ----------------------------
        tenant_id = inputs.get("tenant_id")
        if not tenant_id:
            raise ValueError("❌ GmailTriggerNode: Missing tenant_id.")

        # ----------------------------
        # 2️⃣ Detect Execution Mode
        # ----------------------------
        # AUTO mode = prefetched_events exist (from trigger service)
        # MANUAL mode = no prefetched_events (from execute API)
        is_auto_mode = "prefetched_events" in inputs and inputs["prefetched_events"]
        
        logger.info(f"🔧 Execution Mode: {'AUTO (Trigger Service)' if is_auto_mode else 'MANUAL (Execute API)'}")

        # Create Gmail service instance once for both modes
        gmail_service = GmailService()

        # ----------------------------
        # 3️⃣ AUTO MODE → USE PREFETCHED DATA
        # ----------------------------
        if is_auto_mode:
            logger.info("⚡ GmailTriggerNode running in AUTO mode (prefetched data)")
            return inputs["prefetched_events"]   # return as-is

        # ----------------------------
        # 4️⃣ MANUAL MODE → NORMAL GMAIL FETCH
        # ----------------------------
        form_data = self.form_data or {}
        gmail_cfg = form_data.get("gmail", {})

        if gmail_cfg.get("enableFilters"):
            query = None
            filters = gmail_cfg.get("filters", {})
        else:
            query = gmail_cfg.get("query", "in:inbox category:primary is:unread")
            filters = None

        max_results = int(form_data.get("max_results", 1))

        logger.info(f"🔍 GmailTriggerNode fetching live | query={query}, filters={filters}")
        
        # ✅ Pass execution mode to service (optional params with safe defaults)
        try:
            messages = gmail_service.fetch_messages(
                tenant_id=tenant_id,
                query=query,
                max_results=max_results,
                filters=filters,
                mark_as_read=False,  # ❌ MANUAL mode: DO NOT mark as read
                is_manual_mode=True  # ✅ MANUAL mode: Force unread filter
            )
        except Exception as e:
            # ❌ GRACEFUL ERROR HANDLING - Prevent workflow failure on credential errors
            error_msg = str(e)
            logger.error(f"❌ [GMAIL_TRIGGER] Failed to fetch Gmail messages: {error_msg}")
            
            # Provide helpful debugging information
            if "Credential API failed" in error_msg or "Connection failed" in error_msg:
                logger.warning(
                    "[GMAIL_TRIGGER] ⚠️  CREDENTIAL ERROR DETECTED:\n"
                    "  1. Check if bot-builder-service is running (http://bot-builder-service:5000/health)\n"
                    "  2. Verify tenant_id credentials are configured for Gmail\n"
                    "  3. Check Gmail OAuth token is valid and not expired\n"
                    "  4. Review logs at http://bot-builder-service:5000/tool/Gmail/credentials?tenant_id=%s", 
                    tenant_id
                )
            elif "Missing credentials" in error_msg:
                logger.warning(
                    "[GMAIL_TRIGGER] ⚠️  NO GMAIL CREDENTIALS FOUND:\n"
                    "  Tenant ID %s does not have Gmail credentials configured.\n"
                    "  Please set up Gmail OAuth credentials in the Bot Builder settings.", 
                    tenant_id
                )
            
            logger.info("[GMAIL_TRIGGER] Returning empty results to prevent workflow failure")
            return []  # Return empty array to allow workflow to continue

        # ----------------------------
        # 5️⃣ Return normalized response
        # ----------------------------
        results = []
        for msg in messages:
            results.append({
                "trigger_type": "email",
                "source": "gmail",
                "event": "new_message",
                "metadata": {
                    "message_id": msg.get("message_id"),
                    "timestamp": msg.get("timestamp") or datetime.utcnow().isoformat() + "Z",
                    "from": msg.get("from"),
                    "subject": msg.get("subject"),
                    "attachments": msg.get("attachments", [])
                },
                "content": {
                    "body_text": msg.get("body_text", ""),
                    "attachments": msg.get("attachments", [])
                },
                "context": {
                    "tenant_id": tenant_id,
                    "tool_name": "Gmail"
                }
            })

        logger.info(f"📬 GmailTriggerNode completed — {len(results)} message(s)")
        return results




