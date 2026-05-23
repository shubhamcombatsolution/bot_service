

# from datetime import datetime
# from typing import Dict, Any, List
# from logging_config import setup_logging
# from engine.triggers.base_strategy import BaseTriggerStrategy
# from Tools.GmailTool import GmailTool
# from engine.services.gmail_service import GmailService



# logger = setup_logging("GmailCronStrategy", level="DEBUG")



# class GmailCronStrategy(BaseTriggerStrategy):
#     """
#     Production-ready Gmail polling strategy.
#     🔹 Uses GmailService (same as UI Trigger Node)
#     🔹 No duplicate Gmail processing logic
#     🔹 Fully respects UI filter + schedule settings
#     """
    
#     trigger_type = "gmail"


#     def should_run(self, now: datetime) -> bool:
#         """Decides if trigger should execute based on schedule_meta."""

#         schedule = self.trigger.schedule_meta

#         # NEW CHECK — prevents cron from running event-based triggers
#         if not schedule:
#             logger.debug("[GMAIL_CRON] No schedule defined → treating as event-based trigger → cron skip.")
#             return False

#         mode = schedule.get("mode")
#         hour = schedule.get("hour")
#         minute = schedule.get("minute")
#         weekday = schedule.get("weekday")

#         logger.debug(f"[GMAIL_CRON] Evaluating schedule -> mode={mode}, hr={hour}, min={minute}, weekday={weekday}, now={now}")

#         try:
#             # Helper: Safe int convert
#             def safe_int(value, field_name):
#                 if value is None:
#                     logger.warning(f"[GMAIL_CRON] Missing schedule value '{field_name}'. Skipping trigger.")
#                     return None
#                 try:
#                     return int(value)
#                 except ValueError:
#                     logger.warning(f"[GMAIL_CRON] Invalid schedule value '{field_name}={value}' (not a number).")
#                     return None

#             match mode:

#                 case "everyMinute":
#                     return True  # always run each cycle

#                 case "everyDay":
#                     hr = safe_int(hour, "hour")
#                     mn = safe_int(minute, "minute")
#                     if hr is None or mn is None:
#                         return False
#                     return now.hour == hr and now.minute == mn

#                 case "everyWeek":
#                     if not weekday:
#                         logger.warning("[GMAIL_CRON] Missing 'weekday' for weekly schedule.")
#                         return False

#                     weekday_map = {
#                         "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
#                         "friday": 4, "saturday": 5, "sunday": 6
#                     }

#                     wk = weekday_map.get(str(weekday).lower())
#                     if wk is None:
#                         logger.warning(f"[GMAIL_CRON] Invalid weekday '{weekday}'.")
#                         return False

#                     hr = safe_int(hour, "hour")
#                     mn = safe_int(minute, "minute")
#                     if hr is None or mn is None:
#                         return False

#                     return now.weekday() == wk and now.hour == hr and now.minute == mn

#                 case _:
#                     logger.warning(f"[GMAIL_CRON] Unrecognized mode '{mode}' — skipping.")
#                     return False

#         except Exception as e:
#             logger.exception(f"[GMAIL_CRON] Schedule evaluation failed: {e}")
#             return False
        
#     def fetch_events(self, db_session) -> List[Dict[str, Any]]:
#         tenant_id = self.trigger.tenant_id
#         filters = self.trigger.filter_meta or {}
#         max_results = int(filters.get("max_results", 1))

#         logger.info(
#             f"[GMAIL_CRON] Fetching Gmail events → tenant_id={tenant_id}, filters={filters}"
#         )

#         gmail_service = GmailService()

#         try:
#             # 🔹 GmailService already:
#             #    - builds correct query
#             #    - applies -label:processed_by_agentic
#             #    - marks as read + labels in AUTO mode
#             messages = gmail_service.fetch_messages(
#                 tenant_id=tenant_id,
#                 query=None,
#                 max_results=max_results,
#                 filters=filters,
#                 mark_as_read=False,
#                 is_manual_mode=False,
#             )
#         except Exception as e:
#             logger.exception(f"[GMAIL_CRON] Gmail fetch failed: {e}")
#             return []

#         if not messages:
#             logger.info("[GMAIL_CRON] No new Gmail messages found.")
#             return []

#         events: List[Dict[str, Any]] = []

#         for msg in messages:
#             events.append({
#                 "trigger_type": "email",
#                 "source": "gmail",
#                 "event": "new_message",
#                 "metadata": {
#                     "message_id": msg.get("message_id"),
#                     "thread_id": msg.get("thread_id"),
#                     "timestamp": msg.get("timestamp") or datetime.utcnow().isoformat() + "Z",
#                     "from": msg.get("from"),
#                     "subject": msg.get("subject"),
#                     "attachments": msg.get("attachments", []),
#                 },
#                 "content": {
#                     "body_text": msg.get("body_text", ""),
#                     "attachments": msg.get("attachments", []),
#                 },
#                 "context": {
#                     "tenant_id": tenant_id,
#                     "flow_id": self.trigger.flow_id,
#                     "tool_name": "GmailTool",
#                 },
#             })
#         logger.info(
#             f"[GMAIL_CRON] → {len(events)} event(s) fetched and finalized."
#         )

#         return events

#     # lasted code
#     # def fetch_events(self, db_session) -> List[Dict[str, Any]]:
#     #     tenant_id = self.trigger.tenant_id
#     #     filters = self.trigger.filter_meta or {}
#     #     max_results = int(filters.get("max_results", 1))

#     #     logger.info(f"[GMAIL_CRON] Fetching Gmail events → tenant_id={tenant_id}, filters={filters}")

#     #     gmail_service = GmailService()
        
#     #     # ✅ INITIALIZE GMAIL TOOL FIRST
#     #     try:
#     #         gmail_tool = GmailTool(tenant_id=tenant_id, auth_mode="auto")
#     #         gmail_tool.creds = gmail_service.get_credentials(tenant_id)
#     #         gmail_tool.authenticate()
            
#     #         # ✅ ENSURE LABEL EXISTS BEFORE FETCHING
#     #         label_id = gmail_tool.ensure_label_exists("processed_by_agentic")
            
#     #     except Exception as e:
#     #         logger.error(f"[GMAIL_CRON] Failed to initialize Gmail tool: {e}")
#     #         return []

#     #     try:
#     #         messages = gmail_service.fetch_messages(
#     #             tenant_id=tenant_id,
#     #             query=None,
#     #             max_results=max_results,
#     #             filters=filters
#     #         )
#     #     except Exception as e:
#     #         logger.exception(f"[GMAIL_CRON] Gmail fetch failed: {e}")
#     #         return []

#     #     if not messages:
#     #         return []

#     #     # ✅ IMMEDIATELY LABEL MESSAGES TO PREVENT REPROCESSING
#     #     labeled_messages = []
#     #     for msg in messages:
#     #         try:
#     #             # Apply label and mark as read BEFORE processing
#     #             gmail_tool.modify_message_labels(
#     #                 message_id=msg["message_id"],
#     #                 labels_to_add=[label_id],
#     #                 labels_to_remove=["UNREAD"]
#     #             )
#     #             labeled_messages.append(msg)
#     #             logger.debug(f"[GMAIL_CRON] Labeled message {msg['message_id']}")
                
#     #         except Exception as e:
#     #             logger.error(f"[GMAIL_CRON] Failed to label message {msg.get('message_id')}: {e}")
#     #             # Don't include messages we couldn't label to avoid reprocessing issues
#     #             continue

#     #     logger.info(f"[GMAIL_CRON] Applied labels + marked {len(labeled_messages)} message(s) as read.")

#     #     # ✅ ONLY RETURN SUCCESSFULLY LABELED MESSAGES
#     #     events = []
#     #     for msg in labeled_messages:
#     #         events.append({
#     #             "trigger_type": "email",
#     #             "source": "gmail",
#     #             "event": "new_message",
#     #             "metadata": {
#     #                 "message_id": msg.get("message_id"),
#     #                 "thread_id": msg.get("thread_id"),
#     #                 "timestamp": msg.get("timestamp") or datetime.utcnow().isoformat() + "Z",
#     #                 "from": msg.get("from"),
#     #                 "subject": msg.get("subject"),
#     #                 "attachments": msg.get("attachments", [])
#     #             },
#     #             "content": {
#     #                 "body_text": msg.get("body_text", ""),
#     #                 "attachments": msg.get("attachments", [])
#     #             },
#     #             "context": {
#     #                 "tenant_id": tenant_id,
#     #                 "flow_id": self.trigger.flow_id or "default_flow",
#     #                 "tool_name": "GmailTool"
#     #             }
#     #         })

#     #     logger.info(f"[GMAIL_CRON] → {len(events)} event(s) fetched and finalized.")
#     #     return events
 
#     # lasted old code
#     # def fetch_events(self, db_session) -> List[Dict[str, Any]]:
#     #     """
#     #     Fetch Gmail messages using SAME GmailService logic as UI trigger.
#     #     Ensures filtering & output formatting remain consistent.
#     #     """

#     #     tenant_id = self.trigger.tenant_id
#     #     filters = self.trigger.filter_meta or {}
#     #     max_results = int(filters.get("max_results", 1))

#     #     logger.info(f"[GMAIL_CRON] Fetching Gmail events → tenant_id={tenant_id}, filters={filters}")

#     #     gmail_service = GmailService()

#     #     try:
#     #         # ⬇ SAME INTERNAL PROCESS AS UI Trigger (no duplicate logic)
#     #         messages = gmail_service.fetch_messages(
#     #             tenant_id=tenant_id,
#     #             query=None,            # Service will auto-build based on filters
#     #             max_results=max_results,
#     #             filters=filters
#     #         )

#     #     except Exception as e:
#     #         logger.exception(f"[GMAIL_CRON] Gmail fetch failed: {e}")
#     #         return []

#     #     # Format messages EXACTLY like trigger output
#     #     events = []
#     #     for msg in messages:
#     #         events.append({
#     #             "trigger_type": "email",
#     #             "source": "gmail",
#     #             "event": "new_message",
#     #             "metadata": {
#     #                 "message_id": msg.get("message_id"),
#     #                 "thread_id": msg.get("thread_id"),
#     #                 "timestamp": msg.get("timestamp") or datetime.utcnow().isoformat() + "Z",
#     #                 "from": msg.get("from"),
#     #                 "subject": msg.get("subject"),
#     #                 "attachments": msg.get("attachments", [])
#     #             },
#     #             "content": {
#     #                 "body_text": msg.get("body_text", ""),
#     #                 "attachments": msg.get("attachments", [])
#     #             },
#     #             "context": {
#     #                 "tenant_id": tenant_id,
#     #                 "flow_id": self.trigger.flow_id or "default_flow",
#     #                 "tool_name": "GmailTool"
#     #             }
#     #         })

#     #     logger.info(f"[GMAIL_CRON] → {len(events)} event(s) fetched.")

#     #     return events



from datetime import datetime
from typing import Dict, Any, List
from logging_config import setup_logging
from engine.triggers.base_strategy import BaseTriggerStrategy
from Tools.GmailTool import GmailTool
from engine.services.gmail_service import GmailService



logger = setup_logging("GmailCronStrategy", level="DEBUG")



class GmailCronStrategy(BaseTriggerStrategy):
    """
    Production-ready Gmail polling strategy.
    🔹 Uses GmailService (same as UI Trigger Node)
    🔹 No duplicate Gmail processing logic
    🔹 Fully respects UI filter + schedule settings
    """
    
    trigger_type = "gmail"


    def should_run(self, now: datetime) -> bool:
        """Decides if trigger should execute based on schedule_meta."""

        schedule = self.trigger.schedule_meta

        # NEW CHECK — prevents cron from running event-based triggers
        if not schedule:
            logger.debug("[GMAIL_CRON] No schedule defined → treating as event-based trigger → cron skip.")
            return False

        mode = schedule.get("mode")
        hour = schedule.get("hour")
        minute = schedule.get("minute")
        weekday = schedule.get("weekday")

        logger.debug(f"[GMAIL_CRON] Evaluating schedule -> mode={mode}, hr={hour}, min={minute}, weekday={weekday}, now={now}")

        try:
            # Helper: Safe int convert
            def safe_int(value, field_name):
                if value is None:
                    logger.warning(f"[GMAIL_CRON] Missing schedule value '{field_name}'. Skipping trigger.")
                    return None
                try:
                    return int(value)
                except ValueError:
                    logger.warning(f"[GMAIL_CRON] Invalid schedule value '{field_name}={value}' (not a number).")
                    return None

            match mode:

                case "everyMinute":
                    return True  # always run each cycle

                case "everyDay":
                    hr = safe_int(hour, "hour")
                    mn = safe_int(minute, "minute")
                    if hr is None or mn is None:
                        return False
                    return now.hour == hr and now.minute == mn

                case "everyWeek":
                    if not weekday:
                        logger.warning("[GMAIL_CRON] Missing 'weekday' for weekly schedule.")
                        return False

                    weekday_map = {
                        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                        "friday": 4, "saturday": 5, "sunday": 6
                    }

                    wk = weekday_map.get(str(weekday).lower())
                    if wk is None:
                        logger.warning(f"[GMAIL_CRON] Invalid weekday '{weekday}'.")
                        return False

                    hr = safe_int(hour, "hour")
                    mn = safe_int(minute, "minute")
                    if hr is None or mn is None:
                        return False

                    return now.weekday() == wk and now.hour == hr and now.minute == mn

                case _:
                    logger.warning(f"[GMAIL_CRON] Unrecognized mode '{mode}' — skipping.")
                    return False

        except Exception as e:
            logger.exception(f"[GMAIL_CRON] Schedule evaluation failed: {e}")
            return False
        
    def fetch_events(self, db_session) -> List[Dict[str, Any]]:
        tenant_id = self.trigger.tenant_id
        filters = self.trigger.filter_meta or {}
        max_results = int(filters.get("max_results", 1))

        logger.info(
            f"[GMAIL_CRON] Fetching Gmail events → tenant_id={tenant_id}, filters={filters}"
        )

        gmail_service = GmailService()

        try:
            # 🔹 GmailService already:
            #    - builds correct query
            #    - applies -label:processed_by_agentic
            #    - marks as read + labels in AUTO mode
            messages = gmail_service.fetch_messages(
                tenant_id=tenant_id,
                query=None,
                max_results=max_results,
                filters=filters,
                mark_as_read=False,
                is_manual_mode=False,
            )
        except Exception as e:
            logger.exception(f"[GMAIL_CRON] Gmail fetch failed: {e}")
            return []

        if not messages:
            logger.info("[GMAIL_CRON] No new Gmail messages found.")
            return []

        events: List[Dict[str, Any]] = []

        for msg in messages:
            events.append({
                "trigger_type": "email",
                "source": "gmail",
                "event": "new_message",
                "metadata": {
                    "message_id": msg.get("message_id"),
                    "thread_id": msg.get("thread_id"),
                    "timestamp": msg.get("timestamp") or datetime.utcnow().isoformat() + "Z",
                    "from": msg.get("from"),
                    "subject": msg.get("subject"),
                    "attachments": msg.get("attachments", []),
                },
                "content": {
                    "body_text": msg.get("body_text", ""),
                    "attachments": msg.get("attachments", []),
                },
                "context": {
                    "tenant_id": tenant_id,
                    "flow_id": self.trigger.flow_id,
                    "tool_name": "GmailTool",
                },
            })
        logger.info(
            f"[GMAIL_CRON] → {len(events)} event(s) fetched and finalized."
        )

        return events

    # lasted code
    # def fetch_events(self, db_session) -> List[Dict[str, Any]]:
    #     tenant_id = self.trigger.tenant_id
    #     filters = self.trigger.filter_meta or {}
    #     max_results = int(filters.get("max_results", 1))

    #     logger.info(f"[GMAIL_CRON] Fetching Gmail events → tenant_id={tenant_id}, filters={filters}")

    #     gmail_service = GmailService()
        
    #     # ✅ INITIALIZE GMAIL TOOL FIRST
    #     try:
    #         gmail_tool = GmailTool(tenant_id=tenant_id, auth_mode="auto")
    #         gmail_tool.creds = gmail_service.get_credentials(tenant_id)
    #         gmail_tool.authenticate()
            
    #         # ✅ ENSURE LABEL EXISTS BEFORE FETCHING
    #         label_id = gmail_tool.ensure_label_exists("processed_by_agentic")
            
    #     except Exception as e:
    #         logger.error(f"[GMAIL_CRON] Failed to initialize Gmail tool: {e}")
    #         return []

    #     try:
    #         messages = gmail_service.fetch_messages(
    #             tenant_id=tenant_id,
    #             query=None,
    #             max_results=max_results,
    #             filters=filters
    #         )
    #     except Exception as e:
    #         logger.exception(f"[GMAIL_CRON] Gmail fetch failed: {e}")
    #         return []

    #     if not messages:
    #         return []

    #     # ✅ IMMEDIATELY LABEL MESSAGES TO PREVENT REPROCESSING
    #     labeled_messages = []
    #     for msg in messages:
    #         try:
    #             # Apply label and mark as read BEFORE processing
    #             gmail_tool.modify_message_labels(
    #                 message_id=msg["message_id"],
    #                 labels_to_add=[label_id],
    #                 labels_to_remove=["UNREAD"]
    #             )
    #             labeled_messages.append(msg)
    #             logger.debug(f"[GMAIL_CRON] Labeled message {msg['message_id']}")
                
    #         except Exception as e:
    #             logger.error(f"[GMAIL_CRON] Failed to label message {msg.get('message_id')}: {e}")
    #             # Don't include messages we couldn't label to avoid reprocessing issues
    #             continue

    #     logger.info(f"[GMAIL_CRON] Applied labels + marked {len(labeled_messages)} message(s) as read.")

    #     # ✅ ONLY RETURN SUCCESSFULLY LABELED MESSAGES
    #     events = []
    #     for msg in labeled_messages:
    #         events.append({
    #             "trigger_type": "email",
    #             "source": "gmail",
    #             "event": "new_message",
    #             "metadata": {
    #                 "message_id": msg.get("message_id"),
    #                 "thread_id": msg.get("thread_id"),
    #                 "timestamp": msg.get("timestamp") or datetime.utcnow().isoformat() + "Z",
    #                 "from": msg.get("from"),
    #                 "subject": msg.get("subject"),
    #                 "attachments": msg.get("attachments", [])
    #             },
    #             "content": {
    #                 "body_text": msg.get("body_text", ""),
    #                 "attachments": msg.get("attachments", [])
    #             },
    #             "context": {
    #                 "tenant_id": tenant_id,
    #                 "flow_id": self.trigger.flow_id or "default_flow",
    #                 "tool_name": "GmailTool"
    #             }
    #         })

    #     logger.info(f"[GMAIL_CRON] → {len(events)} event(s) fetched and finalized.")
    #     return events
 
    # lasted old code
    # def fetch_events(self, db_session) -> List[Dict[str, Any]]:
    #     """
    #     Fetch Gmail messages using SAME GmailService logic as UI trigger.
    #     Ensures filtering & output formatting remain consistent.
    #     """

    #     tenant_id = self.trigger.tenant_id
    #     filters = self.trigger.filter_meta or {}
    #     max_results = int(filters.get("max_results", 1))

    #     logger.info(f"[GMAIL_CRON] Fetching Gmail events → tenant_id={tenant_id}, filters={filters}")

    #     gmail_service = GmailService()

    #     try:
    #         # ⬇ SAME INTERNAL PROCESS AS UI Trigger (no duplicate logic)
    #         messages = gmail_service.fetch_messages(
    #             tenant_id=tenant_id,
    #             query=None,            # Service will auto-build based on filters
    #             max_results=max_results,
    #             filters=filters
    #         )

    #     except Exception as e:
    #         logger.exception(f"[GMAIL_CRON] Gmail fetch failed: {e}")
    #         return []

    #     # Format messages EXACTLY like trigger output
    #     events = []
    #     for msg in messages:
    #         events.append({
    #             "trigger_type": "email",
    #             "source": "gmail",
    #             "event": "new_message",
    #             "metadata": {
    #                 "message_id": msg.get("message_id"),
    #                 "thread_id": msg.get("thread_id"),
    #                 "timestamp": msg.get("timestamp") or datetime.utcnow().isoformat() + "Z",
    #                 "from": msg.get("from"),
    #                 "subject": msg.get("subject"),
    #                 "attachments": msg.get("attachments", [])
    #             },
    #             "content": {
    #                 "body_text": msg.get("body_text", ""),
    #                 "attachments": msg.get("attachments", [])
    #             },
    #             "context": {
    #                 "tenant_id": tenant_id,
    #                 "flow_id": self.trigger.flow_id or "default_flow",
    #                 "tool_name": "GmailTool"
    #             }
    #         })

    #     logger.info(f"[GMAIL_CRON] → {len(events)} event(s) fetched.")

    #     return events

