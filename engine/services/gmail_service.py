# import requests
# import base64
# import logging
# from datetime import datetime
# from google.oauth2.credentials import Credentials
# from google.auth.transport.requests import Request
# from bs4 import BeautifulSoup
# from engine import langgraph_urls
# from dateutil import parser
# try:
#     from sqlalchemy.orm import Session
# except Exception:
#     Session = None

# logger = logging.getLogger("GmailService")
# logger.setLevel(logging.DEBUG)


# # class GmailService:

# #     def get_credentials(self, tenant_id: int):
# #         """Fetch and normalize OAuth credentials."""
# #         url = f"{langgraph_urls.GMAIL_CREDENTIALS_URL}?tenant_id={tenant_id}"
# #         logger.debug(f"[GMAIL_SERVICE] Fetching credentials -> {url}")

# #         resp = requests.get(url)

# #         if resp.status_code != 200:
# #             raise Exception(f"[GMAIL_SERVICE] Credential API failed: {resp.text}")

# #         creds_json = resp.json().get("credentials")

# #         if not creds_json:
# #             raise Exception("[GMAIL_SERVICE] Missing credentials JSON")

# #         # Normalize token object
# #         normalized = {
# #             "token": creds_json.get("access_token") or creds_json.get("token"),
# #             "refresh_token": creds_json.get("refresh_token"),
# #             "token_uri": creds_json.get("token_uri"),
# #             "client_id": creds_json.get("client_id"),
# #             "client_secret": creds_json.get("client_secret"),
# #             "scopes": creds_json.get("scopes", ["https://mail.google.com/"])
# #         }

# #         creds = Credentials(**normalized)

# #         # Auto refresh token if expired
# #         if creds.expired and creds.refresh_token:
# #             try:
# #                 creds.refresh(Request())
# #                 logger.info("[GMAIL_SERVICE] Token refreshed successfully")
# #             except Exception as e:
# #                 logger.error(f"[GMAIL_SERVICE] Token refresh failed: {e}")

# #         return creds

# #     def build_query(self, filters: dict, is_manual_mode: bool = False) -> tuple[str, dict]:
# #         """
# #         Convert UI filters to Gmail API query.
        
# #         Args:
# #             filters: Filter dictionary from UI
# #             is_manual_mode: If True (manual execution), override readStatus to 'unread'
# #                            but respect ALL other filters (sender, subject, labels, etc.)
# #         """
# #         q_parts = []
# #         api_params = {}

# #         # If no filters -> default unread inbox
# #         if not filters:
# #             return "in:inbox is:unread", {}

# #         # ✅ Free search text - ALWAYS RESPECT
# #         if filters.get("q"):
# #             q_parts.append(filters["q"])

# #         # ✅ Sender filter - ALWAYS RESPECT
# #         if filters.get("sender"):
# #             senders = [s.strip() for s in filters["sender"].split(",")]
# #             if len(senders) > 1:
# #                 q_parts.append("(" + " OR ".join([f"from:({s})" for s in senders]) + ")")
# #             else:
# #                 q_parts.append(f"from:({senders[0]})")

# #         # ✅ Subject filter - ALWAYS RESPECT
# #         if filters.get("subject"):
# #             q_parts.append(f'subject:"{filters["subject"]}"')

# #         # ⚠️ Read status logic - OVERRIDE IN MANUAL MODE
# #         read_status = filters.get("readStatus")
        
# #         if is_manual_mode:
# #             # ✅ MANUAL MODE: FORCE unread, ignore user's readStatus setting
# #             logger.info("[MANUAL_MODE] Overriding readStatus filter to 'unread' (other filters preserved)")
# #             q_parts.append("is:unread")
# #         else:
# #             # ✅ AUTO MODE: Respect user's readStatus choice
# #             if read_status == "read":
# #                 q_parts.append("-is:unread")
# #             elif read_status == "all":
# #                 pass  # Fetch all
# #             else:
# #                 q_parts.append("is:unread")  # Default unread
        
# #         # ✅ Exclude already processed emails (AUTO mode only)
# #         if not is_manual_mode:
# #             q_parts.append("-label:processed_by_agentic")

# #         # ✅ Drafts - ALWAYS RESPECT
# #         if filters.get("includeDrafts"):
# #             q_parts.append("in:drafts")

# #         # ✅ Spam/Trash - ALWAYS RESPECT
# #         if filters.get("includeSpamTrash"):
# #             api_params["includeSpamTrash"] = True

# #         # ✅ Labels - ALWAYS RESPECT
# #         if filters.get("labelIds"):
# #             api_params["labelIds"] = filters["labelIds"]

# #         # Build final query
# #         final_query = " ".join(q_parts).strip()

# #         if not final_query:
# #             final_query = "in:inbox is:unread"

# #         # Ensure inbox exists if not overridden
# #         if "in:" not in final_query:
# #             final_query = f"in:inbox {final_query}"

# #         logger.debug(f"[BUILD_QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Final Query: {final_query}")
# #         return final_query, api_params

# #     def _extract_message(self, msg_detail: dict) -> dict:
# #         """Extract body and attachments from Gmail API response."""
# #         payload = msg_detail.get("payload", {})
# #         headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

# #         body_text, attachments = self._extract_body_and_attachments(payload)

# #         return {
# #             "message_id": msg_detail.get("id"),
# #             "thread_id": msg_detail.get("threadId"),
# #             "from": headers.get("From"),
# #             "to": headers.get("To"),
# #             "subject": headers.get("Subject"),
# #             "timestamp": headers.get("Date") or datetime.utcnow().isoformat(),
# #             "body_text": body_text,
# #             "attachments": attachments,
# #         }

# #     def _extract_body_and_attachments(self, payload):
# #         """Extract clean text + attachments."""
# #         body_text = ""
# #         attachments = []

# #         def walk(part):
# #             nonlocal body_text, attachments

# #             mime = part.get("mimeType", "")
# #             filename = part.get("filename", "")
# #             body = part.get("body", {})
# #             data = body.get("data")

# #             # Attachments
# #             if filename and mime not in ("text/plain", "text/html"):
# #                 attachments.append({
# #                     "filename": filename,
# #                     "mimetype": mime
# #                 })
# #                 return

# #             # Body Data
# #             if data:
# #                 decoded = base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
# #                 if mime == "text/html":
# #                     decoded = BeautifulSoup(decoded, "html.parser").get_text(separator="\n", strip=True)
# #                 body_text += decoded + "\n"
# #                 return

# #             # Multipart
# #             if mime.startswith("multipart") and "parts" in part:
# #                 for p in part["parts"]:
# #                     walk(p)

# #         walk(payload)
# #         return body_text.strip(), attachments

# #     def _parse_ts(self, ts):
# #         if "(UTC)" in ts:
# #             ts = ts.replace("(UTC)", "").strip()
# #         try:
# #             return parser.parse(ts)
# #         except:
# #             return datetime.utcnow()

# #     def fetch_messages(
# #         self, 
# #         tenant_id, 
# #         query=None, 
# #         max_results=10, 
# #         filters=None,
# #         mark_as_read=True,
# #         is_manual_mode=False
# #     ):
# #         """
# #         Fetch Gmail messages.

# #         Core behavior preserved.
# #         Fix: Do NOT mark more emails than we actually return.
# #         """
# #         from Tools.GmailTool import GmailTool

# #         creds = self.get_credentials(tenant_id)

# #         gmail_tool = GmailTool(tenant_id=tenant_id, auth_mode="auto")
# #         gmail_tool.creds = creds
# #         gmail_tool.authenticate()

# #         # Build query using filter system
# #         # if filters:
# #         #     query, extra_args = self.build_query(filters, is_manual_mode=is_manual_mode)
# #         #     logger.warning(f"[FILTERS] Gmail API Filters → {filters}")
# #         #     logger.warning(f"[QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Query → {query}")
# #         # else:
# #         #     extra_args = {}
# #         query, extra_args = self.build_query(filters or {}, is_manual_mode=is_manual_mode)

# #         logger.debug(f"[GMAIL_SERVICE] Using SEARCH: {query}")

# #         # Ensure label exists BEFORE fetching messages (AUTO mode only)
# #         label_id = None
# #         if mark_as_read and not is_manual_mode:
# #             try:
# #                 label_id = gmail_tool.ensure_label_exists("processed_by_agentic")
# #                 logger.debug(f"[AUTO_MODE] Label 'processed_by_agentic' ready: {label_id}")
# #             except Exception as e:
# #                 logger.error(f"[AUTO_MODE] Failed to ensure label exists: {e}")
# #                 mark_as_read = False

# #         # Fetch more than needed to compensate for Gmail inconsistencies
# #         resp = gmail_tool.list_messages(
# #             query=query,
# #             max_results=max_results * 3,
# #             **extra_args
# #         )

# #         raw_messages = resp.get("messages", []) or []
# #         final_messages = []

# #         labeled_count = 0
# #         failed_count = 0

# #         for msg in raw_messages:
# #             # ✅ HARD STOP: do not process more than max_results
# #             if len(final_messages) >= max_results:
# #                 break

# #             msg_id = msg.get("id")
# #             if not msg_id:
# #                 continue

# #             detail = gmail_tool.get_message(msg_id)
# #             if "error" in detail:
# #                 logger.error(f"[GMAIL_SERVICE] Failed to fetch full message {msg_id}: {detail['error']}")
# #                 continue

# #             full = self._extract_message(detail)

# #             # AUTO mode → mark read + label ONLY for messages we return
# #             if mark_as_read and not is_manual_mode and label_id:
# #                 try:
# #                     gmail_tool.modify_message_labels(
# #                         message_id=msg_id,
# #                         labels_to_add=[label_id],
# #                         labels_to_remove=["UNREAD"]
# #                     )
# #                     labeled_count += 1
# #                     logger.debug(f"[AUTO_MODE] Marked message {msg_id} as read and labeled")
# #                 except AttributeError as ae:
# #                     logger.error(f"[AUTO_MODE] Method 'modify_message_labels' not found: {ae}")
# #                     failed_count += 1
# #                     continue
# #                 except Exception as e:
# #                     logger.warning(f"[AUTO_MODE] Failed to mark message {msg_id}: {e}")
# #                     failed_count += 1
# #                     continue

# #             # Manual mode OR successful AUTO mode
# #             final_messages.append(full)

# #         # Log labeling statistics
# #         if not is_manual_mode and (labeled_count > 0 or failed_count > 0):
# #             logger.info(f"[AUTO_MODE] Labeling stats: {labeled_count} succeeded, {failed_count} failed")
# #             if failed_count > 0:
# #                 logger.warning(f"[AUTO_MODE] {failed_count} messages excluded to prevent reprocessing")

# #         # Sort by timestamp descending (unchanged)
# #         final_messages.sort(
# #             key=lambda x: self._parse_ts(x["timestamp"]),
# #             reverse=True
# #         )

# #         logger.info(
# #             f"[GMAIL_SERVICE] Returning {len(final_messages)} message(s) | "
# #             f"Mode={'MANUAL' if is_manual_mode else 'AUTO'}"
# #         )

# #         return final_messages




















# # class GmailService:

# #     def get_credentials(self, tenant_id: int):
# #         """Fetch and normalize OAuth credentials."""
# #         url = f"{langgraph_urls.GMAIL_CREDENTIALS_URL}?tenant_id={tenant_id}"
# #         logger.debug(f"[GMAIL_SERVICE] Fetching credentials -> {url}")

# #         try:
# #             resp = requests.get(url, timeout=10)
# #         except requests.ConnectionError as e:
# #             raise Exception(
# #                 f"[GMAIL_SERVICE] Connection failed to credential endpoint ({url}). "
# #                 f"Error: {e}. "
# #                 f"Ensure bot-builder-service is running and accessible."
# #             )
# #         except requests.Timeout as e:
# #             raise Exception(
# #                 f"[GMAIL_SERVICE] Credential endpoint timeout ({url}). "
# #                 f"Service took too long to respond. Error: {e}"
# #             )
# #         except Exception as e:
# #             raise Exception(
# #                 f"[GMAIL_SERVICE] Failed to fetch credentials from {url}. Error: {e}"
# #             )

# #         if resp.status_code != 200:
# #             error_detail = resp.text[:500] if resp.text else "No error details"
# #             raise Exception(
# #                 f"[GMAIL_SERVICE] Credential API failed with status {resp.status_code}. "
# #                 f"Endpoint: {url} | Response: {error_detail}"
# #             )

# #         creds_json = resp.json().get("credentials")

# #         if not creds_json:
# #             raise Exception(
# #                 f"[GMAIL_SERVICE] Missing 'credentials' in response from {url}. "
# #                 f"Verify tenant_id={tenant_id} has valid Gmail credentials configured."
# #             )

# #         # Normalize token object
# #         normalized = {
# #             "token": creds_json.get("access_token") or creds_json.get("token"),
# #             "refresh_token": creds_json.get("refresh_token"),
# #             "token_uri": creds_json.get("token_uri"),
# #             "client_id": creds_json.get("client_id"),
# #             "client_secret": creds_json.get("client_secret"),
# #             "scopes": creds_json.get("scopes", ["https://mail.google.com/"])
# #         }

# #         creds = Credentials(**normalized)

# #         # Auto refresh token if expired
# #         if creds.expired and creds.refresh_token:
# #             try:
# #                 creds.refresh(Request())
# #                 logger.info("[GMAIL_SERVICE] Token refreshed successfully")
# #             except Exception as e:
# #                 logger.error(f"[GMAIL_SERVICE] Token refresh failed: {e}")

# #         return creds

# #     def build_query(self, filters: dict, is_manual_mode: bool = False) -> tuple[str, dict]:
# #         """
# #         Convert UI filters to Gmail API query.
        
# #         Args:
# #             filters: Filter dictionary from UI
# #             is_manual_mode: If True (manual execution), override readStatus to 'unread'
# #                            but respect ALL other filters (sender, subject, labels, etc.)
# #         """
# #         q_parts = []
# #         api_params = {}

# #         # If no filters -> default unread inbox
# #         if not filters:
# #             return "in:inbox is:unread", {}

# #         # ✅ Free search text - ALWAYS RESPECT
# #         if filters.get("q"):
# #             q_parts.append(filters["q"])

# #         # ✅ Sender filter - ALWAYS RESPECT
# #         if filters.get("sender"):
# #             senders = [s.strip() for s in filters["sender"].split(",")]
# #             if len(senders) > 1:
# #                 q_parts.append("(" + " OR ".join([f"from:({s})" for s in senders]) + ")")
# #             else:
# #                 q_parts.append(f"from:({senders[0]})")

# #         # ✅ Subject filter - ALWAYS RESPECT
# #         if filters.get("subject"):
# #             q_parts.append(f'subject:"{filters["subject"]}"')

# #         # ⚠️ Read status logic - OVERRIDE IN MANUAL MODE
# #         read_status = filters.get("readStatus")
        
# #         if is_manual_mode:
# #             # ✅ MANUAL MODE: FORCE unread, ignore user's readStatus setting
# #             logger.info("[MANUAL_MODE] Overriding readStatus filter to 'unread' (other filters preserved)")
# #             q_parts.append("is:unread")
# #         else:
# #             # ✅ AUTO MODE: Respect user's readStatus choice
# #             if read_status == "read":
# #                 q_parts.append("-is:unread")
# #             elif read_status == "all":
# #                 pass  # Fetch all
# #             else:
# #                 q_parts.append("is:unread")  # Default unread
        
# #         # ✅ Exclude already processed emails (AUTO mode only)
# #         if not is_manual_mode:
# #             q_parts.append("-label:processed_by_agentic")

# #         # ✅ Drafts - ALWAYS RESPECT
# #         if filters.get("includeDrafts"):
# #             q_parts.append("in:drafts")

# #         # ✅ Spam/Trash - ALWAYS RESPECT
# #         if filters.get("includeSpamTrash"):
# #             api_params["includeSpamTrash"] = True

# #         # ✅ Labels - ALWAYS RESPECT
# #         if filters.get("labelIds"):
# #             api_params["labelIds"] = filters["labelIds"]

# #         # Build final query
# #         final_query = " ".join(q_parts).strip()

# #         if not final_query:
# #             final_query = "in:inbox is:unread"

# #         # Ensure inbox exists if not overridden
# #         if "in:" not in final_query:
# #             final_query = f"in:inbox {final_query}"

# #         logger.debug(f"[BUILD_QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Final Query: {final_query}")
# #         return final_query, api_params

# #     def _extract_message(self, msg_detail: dict) -> dict:
# #         """Extract body and attachments from Gmail API response."""
# #         payload = msg_detail.get("payload", {})
# #         headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

# #         body_text, attachments = self._extract_body_and_attachments(payload)

# #         return {
# #             "message_id": msg_detail.get("id"),
# #             "thread_id": msg_detail.get("threadId"),
# #             "from": headers.get("From"),
# #             "to": headers.get("To"),
# #             "subject": headers.get("Subject"),
# #             "timestamp": headers.get("Date") or datetime.utcnow().isoformat(),
# #             "body_text": body_text,
# #             "attachments": attachments,
# #         }

# #     def _extract_body_and_attachments(self, payload):
# #         """Extract clean text + attachments."""
# #         body_text = ""
# #         attachments = []

# #         def walk(part):
# #             nonlocal body_text, attachments

# #             mime = part.get("mimeType", "")
# #             filename = part.get("filename", "")
# #             body = part.get("body", {})
# #             data = body.get("data")

# #             # Attachments
# #             if filename and mime not in ("text/plain", "text/html"):
# #                 attachments.append({
# #                     "filename": filename,
# #                     "mimetype": mime
# #                 })
# #                 return

# #             # Body Data
# #             if data:
# #                 decoded = base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
# #                 if mime == "text/html":
# #                     decoded = BeautifulSoup(decoded, "html.parser").get_text(separator="\n", strip=True)
# #                 body_text += decoded + "\n"
# #                 return

# #             # Multipart
# #             if mime.startswith("multipart") and "parts" in part:
# #                 for p in part["parts"]:
# #                     walk(p)

# #         walk(payload)
# #         return body_text.strip(), attachments

# #     def _parse_ts(self, ts):
# #         if "(UTC)" in ts:
# #             ts = ts.replace("(UTC)", "").strip()
# #         try:
# #             return parser.parse(ts)
# #         except:
# #             return datetime.utcnow()
        
# #     def fetch_messages(
# #         self, 
# #         tenant_id, 
# #         query=None, 
# #         max_results=10, 
# #         filters=None,
# #         mark_as_read=True,
# #         is_manual_mode=False
# #     ):
# #         """
# #         Fetch Gmail messages.

# #         Core behavior preserved.
# #         Fix: Do NOT mark more emails than we actually return.
# #         """
# #         from Tools.GmailTool import GmailTool

# #         creds = self.get_credentials(tenant_id)

# #         gmail_tool = GmailTool(tenant_id=tenant_id, auth_mode="auto")
# #         gmail_tool.creds = creds
# #         gmail_tool.authenticate()

# #         # Build query using filter system
# #         # if filters:
# #         #     query, extra_args = self.build_query(filters, is_manual_mode=is_manual_mode)
# #         #     logger.warning(f"[FILTERS] Gmail API Filters → {filters}")
# #         #     logger.warning(f"[QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Query → {query}")
# #         # else:
# #         #     extra_args = {}
# #         query, extra_args = self.build_query(filters or {}, is_manual_mode=is_manual_mode)

# #         logger.debug(f"[GMAIL_SERVICE] Using SEARCH: {query}")

# #         # Ensure label exists BEFORE fetching messages (AUTO mode only)
# #         label_id = None
# #         if mark_as_read and not is_manual_mode:
# #             try:
# #                 label_id = gmail_tool.ensure_label_exists("processed_by_agentic")
# #                 logger.debug(f"[AUTO_MODE] Label 'processed_by_agentic' ready: {label_id}")
# #             except Exception as e:
# #                 logger.error(f"[AUTO_MODE] Failed to ensure label exists: {e}")
# #                 mark_as_read = False

# #         # Fetch more than needed to compensate for Gmail inconsistencies
# #         resp = gmail_tool.list_messages(
# #             query=query,
# #             max_results=max_results * 3,
# #             **extra_args
# #         )

# #         raw_messages = resp.get("messages", []) or []
# #         final_messages = []

# #         labeled_count = 0
# #         failed_count = 0

# #         for msg in raw_messages:
# #             # ✅ HARD STOP: do not process more than max_results
# #             if len(final_messages) >= max_results:
# #                 break

# #             msg_id = msg.get("id")
# #             if not msg_id:
# #                 continue

# #             detail = gmail_tool.get_message(msg_id)
# #             if "error" in detail:
# #                 logger.error(f"[GMAIL_SERVICE] Failed to fetch full message {msg_id}: {detail['error']}")
# #                 continue

# #             full = self._extract_message(detail)

# #             # AUTO mode → mark read + label ONLY for messages we return
# #             if mark_as_read and not is_manual_mode and label_id:
# #                 try:
# #                     gmail_tool.modify_message_labels(
# #                         message_id=msg_id,
# #                         labels_to_add=[label_id],
# #                         labels_to_remove=["UNREAD"]
# #                     )
# #                     labeled_count += 1
# #                     logger.debug(f"[AUTO_MODE] Marked message {msg_id} as read and labeled")
# #                 except AttributeError as ae:
# #                     logger.error(f"[AUTO_MODE] Method 'modify_message_labels' not found: {ae}")
# #                     failed_count += 1
# #                     continue
# #                 except Exception as e:
# #                     logger.warning(f"[AUTO_MODE] Failed to mark message {msg_id}: {e}")
# #                     failed_count += 1
# #                     continue

# #             # Manual mode OR successful AUTO mode
# #             final_messages.append(full)

# #         # Log labeling statistics
# #         if not is_manual_mode and (labeled_count > 0 or failed_count > 0):
# #             logger.info(f"[AUTO_MODE] Labeling stats: {labeled_count} succeeded, {failed_count} failed")
# #             if failed_count > 0:
# #                 logger.warning(f"[AUTO_MODE] {failed_count} messages excluded to prevent reprocessing")

# #         # Sort by timestamp descending (unchanged)
# #         final_messages.sort(
# #             key=lambda x: self._parse_ts(x["timestamp"]),
# #             reverse=True
# #         )

# #         logger.info(
# #             f"[GMAIL_SERVICE] Returning {len(final_messages)} message(s) | "
# #             f"Mode={'MANUAL' if is_manual_mode else 'AUTO'}"
# #         )

# #         return final_messages
















#     #lasted Code  
#     # def fetch_messages(
#     #     self, 
#     #     tenant_id, 
#     #     query=None, 
#     #     max_results=10, 
#     #     filters=None,
#     #     mark_as_read=True,
#     #     is_manual_mode=False
#     # ):
#     #     """
#     #     Fetch Gmail messages.
        
#     #     Args:
#     #         tenant_id: Tenant ID for authentication
#     #         query: Gmail search query string
#     #         max_results: Maximum number of results to return
#     #         filters: Filter dictionary from UI
#     #         mark_as_read: Optional. If True, mark emails as read and add label (AUTO mode)
#     #                     If False, don't modify emails (MANUAL mode). Default: True
#     #         is_manual_mode: Optional. If True, force unread filter regardless of user settings.
#     #                     If False, respect user's readStatus filter. Default: False
#     #     """
#     #     from Tools.GmailTool import GmailTool

#     #     creds = self.get_credentials(tenant_id)

#     #     gmail_tool = GmailTool(tenant_id=tenant_id, auth_mode="auto")
#     #     gmail_tool.creds = creds
#     #     gmail_tool.authenticate()

#     #     # Build query using filter system
#     #     if filters:
#     #         query, extra_args = self.build_query(filters, is_manual_mode=is_manual_mode)
#     #         logger.warning(f"[FILTERS] Gmail API Filters → {filters}")
#     #         logger.warning(f"[QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Query → {query}")
#     #     else:
#     #         extra_args = {}
        
#     #     logger.debug(f"[GMAIL_SERVICE] Using SEARCH: {query}")
        
#     #     # ✅ Ensure label exists BEFORE fetching messages (AUTO mode only)
#     #     label_id = None
#     #     if mark_as_read and not is_manual_mode:
#     #         try:
#     #             label_id = gmail_tool.ensure_label_exists("processed_by_agentic")
#     #             logger.debug(f"[AUTO_MODE] Label 'processed_by_agentic' ready: {label_id}")
#     #         except Exception as e:
#     #             logger.error(f"[AUTO_MODE] Failed to ensure label exists: {e}")
#     #             # Continue without labeling if label creation fails
#     #             mark_as_read = False
        
#     #     resp = gmail_tool.list_messages(
#     #         query=query,
#     #         max_results=max_results * 3,
#     #         **extra_args
#     #     )

#     #     raw_messages = resp.get("messages", []) or []
#     #     final_messages = []
        
#     #     # Track labeling success
#     #     labeled_count = 0
#     #     failed_count = 0

#     #     for msg in raw_messages:
#     #         msg_id = msg.get("id")
#     #         if not msg_id:
#     #             continue

#     #         detail = gmail_tool.get_message(msg_id)

#     #         if "error" in detail:
#     #             logger.error(f"[GMAIL_SERVICE] Failed to fetch full message {msg_id}: {detail['error']}")
#     #             continue

#     #         full = self._extract_message(detail)
            
#     #         # ✅ Mark as read and add label ONLY in AUTO mode
#     #         if mark_as_read and not is_manual_mode and label_id:
#     #             try:
#     #                 # Mark as read AND add processed label in ONE call
#     #                 gmail_tool.modify_message_labels(
#     #                     message_id=msg_id,
#     #                     labels_to_add=[label_id],
#     #                     labels_to_remove=["UNREAD"]
#     #                 )
                    
#     #                 labeled_count += 1
#     #                 logger.debug(f"[AUTO_MODE] Marked message {msg_id} as read and labeled")
                    
#     #                 # Only add successfully labeled messages to results
#     #                 final_messages.append(full)
                    
#     #             except AttributeError as ae:
#     #                 logger.error(f"[AUTO_MODE] Method 'modify_message_labels' not found: {ae}")
#     #                 failed_count += 1
#     #                 # CRITICAL: Don't add this message to avoid reprocessing
#     #                 continue
#     #             except Exception as e:
#     #                 logger.warning(f"[AUTO_MODE] Failed to mark message {msg_id}: {e}")
#     #                 failed_count += 1
#     #                 # Don't add this message to results if we couldn't mark it
#     #                 continue
#     #         else:
#     #             # Manual mode - add all messages without marking
#     #             final_messages.append(full)

#     #     # Log labeling statistics (AUTO mode)
#     #     if not is_manual_mode and (labeled_count > 0 or failed_count > 0):
#     #         logger.info(f"[AUTO_MODE] Labeling stats: {labeled_count} succeeded, {failed_count} failed")
#     #         if failed_count > 0:
#     #             logger.warning(f"[AUTO_MODE] {failed_count} messages excluded to prevent reprocessing")

#     #     # Sort by timestamp descending
#     #     final_messages.sort(
#     #         key=lambda x: self._parse_ts(x["timestamp"]),
#     #         reverse=True
#     #     )
        
#     #     # Limit to requested count
#     #     final_messages = final_messages[:max_results]

#     #     logger.info(f"[GMAIL_SERVICE] Returning {len(final_messages)} message(s) | Mode={'MANUAL' if is_manual_mode else 'AUTO'}")
#     #     return final_messages










# class GmailService:

#     def get_credentials(self, tenant_id: int):
#         """Fetch and normalize OAuth credentials."""
#         url = f"{langgraph_urls.GMAIL_CREDENTIALS_URL}?tenant_id={tenant_id}"
#         logger.debug(f"[GMAIL_SERVICE] Fetching credentials -> {url}")

#         resp = requests.get(url)

#         if resp.status_code != 200:
#             raise Exception(f"[GMAIL_SERVICE] Credential API failed: {resp.text}")

#         creds_json = resp.json().get("credentials")

#         if not creds_json:
#             raise Exception("[GMAIL_SERVICE] Missing credentials JSON")

#         # # Normalize token object
#         # normalized = {
#         #     "token": creds_json.get("access_token") or creds_json.get("token"),
#         #     "refresh_token": creds_json.get("refresh_token"),
#         #     "token_uri": creds_json.get("token_uri"),
#         #     "client_id": creds_json.get("client_id"),
#         #     "client_secret": creds_json.get("client_secret"),
#         #     "scopes": creds_json.get("scopes", ["https://mail.google.com/"])
#         # }
#         token_value = (
#             creds_json.get("token")
#             or creds_json.get("access_token")
#             or creds_json.get("accessToken")
#             or creds_json.get("oauth_token")
#         )

#         if not token_value:
#             raise Exception(f"[GMAIL_SERVICE] token field missing for tenant_id={tenant_id}")

#         normalized = {
#             "token": token_value,
#             "refresh_token": creds_json.get("refresh_token") or creds_json.get("refreshToken"),
#             "token_uri": creds_json.get("token_uri") or "https://oauth2.googleapis.com/token",
#             "client_id": creds_json.get("client_id"),
#             "client_secret": creds_json.get("client_secret"),
#             "scopes": creds_json.get("scopes", ["https://mail.google.com/"]),
#         }
#         creds = Credentials(**normalized)

#         # Auto refresh token if expired
#         if creds.expired and creds.refresh_token:
#             try:
#                 creds.refresh(Request())
#                 logger.info("[GMAIL_SERVICE] Token refreshed successfully")
#             except Exception as e:
#                 logger.error(f"[GMAIL_SERVICE] Token refresh failed: {e}")

#         return creds

#     def build_query(self, filters: dict, is_manual_mode: bool = False) -> tuple[str, dict]:
#         """
#         Convert UI filters to Gmail API query.
        
#         Args:
#             filters: Filter dictionary from UI
#             is_manual_mode: If True (manual execution), override readStatus to 'unread'
#                            but respect ALL other filters (sender, subject, labels, etc.)
#         """
#         q_parts = []
#         api_params = {}

#         # If no filters -> default unread inbox
#         if not filters:
#             return "in:inbox is:unread", {}

#         # ✅ Free search text - ALWAYS RESPECT
#         if filters.get("q"):
#             q_parts.append(filters["q"])

#         # ✅ Sender filter - ALWAYS RESPECT
#         if filters.get("sender"):
#             senders = [s.strip() for s in filters["sender"].split(",")]
#             if len(senders) > 1:
#                 q_parts.append("(" + " OR ".join([f"from:({s})" for s in senders]) + ")")
#             else:
#                 q_parts.append(f"from:({senders[0]})")

#         # ✅ Subject filter - ALWAYS RESPECT
#         if filters.get("subject"):
#             q_parts.append(f'subject:"{filters["subject"]}"')

#         # ⚠️ Read status logic - OVERRIDE IN MANUAL MODE
#         read_status = filters.get("readStatus")
        
#         if is_manual_mode:
#             # ✅ MANUAL MODE: FORCE unread, ignore user's readStatus setting
#             logger.info("[MANUAL_MODE] Overriding readStatus filter to 'unread' (other filters preserved)")
#             q_parts.append("is:unread")
#         else:
#             # ✅ AUTO MODE: Respect user's readStatus choice
#             if read_status == "read":
#                 q_parts.append("-is:unread")
#             elif read_status == "all":
#                 pass  # Fetch all
#             else:
#                 q_parts.append("is:unread")  # Default unread
        
#         # ✅ Exclude already processed emails (AUTO mode only)
#         if not is_manual_mode:
#             q_parts.append("-label:processed_by_agentic")

#         # ✅ Drafts - ALWAYS RESPECT
#         if filters.get("includeDrafts"):
#             q_parts.append("in:drafts")

#         # ✅ Spam/Trash - ALWAYS RESPECT
#         if filters.get("includeSpamTrash"):
#             api_params["includeSpamTrash"] = True

#         # ✅ Labels - ALWAYS RESPECT
#         if filters.get("labelIds"):
#             api_params["labelIds"] = filters["labelIds"]

#         # Build final query
#         final_query = " ".join(q_parts).strip()

#         if not final_query:
#             final_query = "in:inbox is:unread"

#         # Ensure inbox exists if not overridden
#         if "in:" not in final_query:
#             final_query = f"in:inbox {final_query}"

#         logger.debug(f"[BUILD_QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Final Query: {final_query}")
#         return final_query, api_params

#     def _extract_message(self, msg_detail: dict) -> dict:
#         """Extract body and attachments from Gmail API response."""
#         payload = msg_detail.get("payload", {})
#         headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

#         body_text, attachments = self._extract_body_and_attachments(payload)

#         return {
#             "message_id": msg_detail.get("id"),
#             "thread_id": msg_detail.get("threadId"),
#             "from": headers.get("From"),
#             "to": headers.get("To"),
#             "subject": headers.get("Subject"),
#             "timestamp": headers.get("Date") or datetime.utcnow().isoformat(),
#             "body_text": body_text,
#             "attachments": attachments,
#         }

#     def _extract_body_and_attachments(self, payload):
#         """Extract clean text + attachments."""
#         body_text = ""
#         attachments = []

#         def walk(part):
#             nonlocal body_text, attachments

#             mime = part.get("mimeType", "")
#             filename = part.get("filename", "")
#             body = part.get("body", {})
#             data = body.get("data")

#             # Attachments
#             if filename and mime not in ("text/plain", "text/html"):
#                 attachments.append({
#                     "filename": filename,
#                     "mimetype": mime
#                 })
#                 return

#             # Body Data
#             if data:
#                 decoded = base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
#                 if mime == "text/html":
#                     decoded = BeautifulSoup(decoded, "html.parser").get_text(separator="\n", strip=True)
#                 body_text += decoded + "\n"
#                 return

#             # Multipart
#             if mime.startswith("multipart") and "parts" in part:
#                 for p in part["parts"]:
#                     walk(p)

#         walk(payload)
#         return body_text.strip(), attachments

#     def _parse_ts(self, ts):
#         if "(UTC)" in ts:
#             ts = ts.replace("(UTC)", "").strip()
#         try:
#             return parser.parse(ts)
#         except:
#             return datetime.utcnow()
        
#     def fetch_messages(
#         self, 
#         tenant_id, 
#         query=None, 
#         max_results=10, 
#         filters=None,
#         mark_as_read=True,
#         is_manual_mode=False
#     ):
#         """
#         Fetch Gmail messages.

#         Core behavior preserved.
#         Fix: Do NOT mark more emails than we actually return.
#         """
#         from Tools.GmailTool import GmailTool

#         creds = self.get_credentials(tenant_id)

#         gmail_tool = GmailTool(tenant_id=tenant_id, auth_mode="auto")
#         gmail_tool.creds = creds
#         gmail_tool.authenticate()

#         # Build query using filter system
#         # if filters:
#         #     query, extra_args = self.build_query(filters, is_manual_mode=is_manual_mode)
#         #     logger.warning(f"[FILTERS] Gmail API Filters → {filters}")
#         #     logger.warning(f"[QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Query → {query}")
#         # else:
#         #     extra_args = {}
#         query, extra_args = self.build_query(filters or {}, is_manual_mode=is_manual_mode)

#         logger.debug(f"[GMAIL_SERVICE] Using SEARCH: {query}")

#         # Ensure label exists BEFORE fetching messages (AUTO mode only)
#         label_id = None
#         if mark_as_read and not is_manual_mode:
#             try:
#                 label_id = gmail_tool.ensure_label_exists("processed_by_agentic")
#                 logger.debug(f"[AUTO_MODE] Label 'processed_by_agentic' ready: {label_id}")
#             except Exception as e:
#                 logger.error(f"[AUTO_MODE] Failed to ensure label exists: {e}")
#                 mark_as_read = False

#         # Fetch more than needed to compensate for Gmail inconsistencies
#         resp = gmail_tool.list_messages(
#             query=query,
#             max_results=max_results * 3,
#             **extra_args
#         )

#         raw_messages = resp.get("messages", []) or []
#         final_messages = []

#         labeled_count = 0
#         failed_count = 0

#         for msg in raw_messages:
#             # ✅ HARD STOP: do not process more than max_results
#             if len(final_messages) >= max_results:
#                 break

#             msg_id = msg.get("id")
#             if not msg_id:
#                 continue

#             detail = gmail_tool.get_message(msg_id)
#             if "error" in detail:
#                 logger.error(f"[GMAIL_SERVICE] Failed to fetch full message {msg_id}: {detail['error']}")
#                 continue

#             full = self._extract_message(detail)

#             # AUTO mode → mark read + label ONLY for messages we return
#             if mark_as_read and not is_manual_mode and label_id:
#                 try:
#                     gmail_tool.modify_message_labels(
#                         message_id=msg_id,
#                         labels_to_add=[label_id],
#                         labels_to_remove=["UNREAD"]
#                     )
#                     labeled_count += 1
#                     logger.debug(f"[AUTO_MODE] Marked message {msg_id} as read and labeled")
#                 except AttributeError as ae:
#                     logger.error(f"[AUTO_MODE] Method 'modify_message_labels' not found: {ae}")
#                     failed_count += 1
#                     continue
#                 except Exception as e:
#                     logger.warning(f"[AUTO_MODE] Failed to mark message {msg_id}: {e}")
#                     failed_count += 1
#                     continue

#             # Manual mode OR successful AUTO mode
#             final_messages.append(full)

#         # Log labeling statistics
#         if not is_manual_mode and (labeled_count > 0 or failed_count > 0):
#             logger.info(f"[AUTO_MODE] Labeling stats: {labeled_count} succeeded, {failed_count} failed")
#             if failed_count > 0:
#                 logger.warning(f"[AUTO_MODE] {failed_count} messages excluded to prevent reprocessing")

#         # Sort by timestamp descending (unchanged)
#         final_messages.sort(
#             key=lambda x: self._parse_ts(x["timestamp"]),
#             reverse=True
#         )

#         logger.info(
#             f"[GMAIL_SERVICE] Returning {len(final_messages)} message(s) | "
#             f"Mode={'MANUAL' if is_manual_mode else 'AUTO'}"
#         )

#         return final_messages
import requests
import base64
import logging
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from bs4 import BeautifulSoup
from engine import langgraph_urls
from dateutil import parser
try:
    from sqlalchemy.orm import Session
except Exception:
    Session = None

logger = logging.getLogger("GmailService")
logger.setLevel(logging.DEBUG)


# class GmailService:

#     def get_credentials(self, tenant_id: int):
#         """Fetch and normalize OAuth credentials."""
#         url = f"{langgraph_urls.GMAIL_CREDENTIALS_URL}?tenant_id={tenant_id}"
#         logger.debug(f"[GMAIL_SERVICE] Fetching credentials -> {url}")

#         resp = requests.get(url)

#         if resp.status_code != 200:
#             raise Exception(f"[GMAIL_SERVICE] Credential API failed: {resp.text}")

#         creds_json = resp.json().get("credentials")

#         if not creds_json:
#             raise Exception("[GMAIL_SERVICE] Missing credentials JSON")

#         # Normalize token object
#         normalized = {
#             "token": creds_json.get("access_token") or creds_json.get("token"),
#             "refresh_token": creds_json.get("refresh_token"),
#             "token_uri": creds_json.get("token_uri"),
#             "client_id": creds_json.get("client_id"),
#             "client_secret": creds_json.get("client_secret"),
#             "scopes": creds_json.get("scopes", ["https://mail.google.com/"])
#         }

#         creds = Credentials(**normalized)

#         # Auto refresh token if expired
#         if creds.expired and creds.refresh_token:
#             try:
#                 creds.refresh(Request())
#                 logger.info("[GMAIL_SERVICE] Token refreshed successfully")
#             except Exception as e:
#                 logger.error(f"[GMAIL_SERVICE] Token refresh failed: {e}")

#         return creds

#     def build_query(self, filters: dict, is_manual_mode: bool = False) -> tuple[str, dict]:
#         """
#         Convert UI filters to Gmail API query.
        
#         Args:
#             filters: Filter dictionary from UI
#             is_manual_mode: If True (manual execution), override readStatus to 'unread'
#                            but respect ALL other filters (sender, subject, labels, etc.)
#         """
#         q_parts = []
#         api_params = {}

#         # If no filters -> default unread inbox
#         if not filters:
#             return "in:inbox is:unread", {}

#         # ✅ Free search text - ALWAYS RESPECT
#         if filters.get("q"):
#             q_parts.append(filters["q"])

#         # ✅ Sender filter - ALWAYS RESPECT
#         if filters.get("sender"):
#             senders = [s.strip() for s in filters["sender"].split(",")]
#             if len(senders) > 1:
#                 q_parts.append("(" + " OR ".join([f"from:({s})" for s in senders]) + ")")
#             else:
#                 q_parts.append(f"from:({senders[0]})")

#         # ✅ Subject filter - ALWAYS RESPECT
#         if filters.get("subject"):
#             q_parts.append(f'subject:"{filters["subject"]}"')

#         # ⚠️ Read status logic - OVERRIDE IN MANUAL MODE
#         read_status = filters.get("readStatus")
        
#         if is_manual_mode:
#             # ✅ MANUAL MODE: FORCE unread, ignore user's readStatus setting
#             logger.info("[MANUAL_MODE] Overriding readStatus filter to 'unread' (other filters preserved)")
#             q_parts.append("is:unread")
#         else:
#             # ✅ AUTO MODE: Respect user's readStatus choice
#             if read_status == "read":
#                 q_parts.append("-is:unread")
#             elif read_status == "all":
#                 pass  # Fetch all
#             else:
#                 q_parts.append("is:unread")  # Default unread
        
#         # ✅ Exclude already processed emails (AUTO mode only)
#         if not is_manual_mode:
#             q_parts.append("-label:processed_by_agentic")

#         # ✅ Drafts - ALWAYS RESPECT
#         if filters.get("includeDrafts"):
#             q_parts.append("in:drafts")

#         # ✅ Spam/Trash - ALWAYS RESPECT
#         if filters.get("includeSpamTrash"):
#             api_params["includeSpamTrash"] = True

#         # ✅ Labels - ALWAYS RESPECT
#         if filters.get("labelIds"):
#             api_params["labelIds"] = filters["labelIds"]

#         # Build final query
#         final_query = " ".join(q_parts).strip()

#         if not final_query:
#             final_query = "in:inbox is:unread"

#         # Ensure inbox exists if not overridden
#         if "in:" not in final_query:
#             final_query = f"in:inbox {final_query}"

#         logger.debug(f"[BUILD_QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Final Query: {final_query}")
#         return final_query, api_params

#     def _extract_message(self, msg_detail: dict) -> dict:
#         """Extract body and attachments from Gmail API response."""
#         payload = msg_detail.get("payload", {})
#         headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

#         body_text, attachments = self._extract_body_and_attachments(payload)

#         return {
#             "message_id": msg_detail.get("id"),
#             "thread_id": msg_detail.get("threadId"),
#             "from": headers.get("From"),
#             "to": headers.get("To"),
#             "subject": headers.get("Subject"),
#             "timestamp": headers.get("Date") or datetime.utcnow().isoformat(),
#             "body_text": body_text,
#             "attachments": attachments,
#         }

#     def _extract_body_and_attachments(self, payload):
#         """Extract clean text + attachments."""
#         body_text = ""
#         attachments = []

#         def walk(part):
#             nonlocal body_text, attachments

#             mime = part.get("mimeType", "")
#             filename = part.get("filename", "")
#             body = part.get("body", {})
#             data = body.get("data")

#             # Attachments
#             if filename and mime not in ("text/plain", "text/html"):
#                 attachments.append({
#                     "filename": filename,
#                     "mimetype": mime
#                 })
#                 return

#             # Body Data
#             if data:
#                 decoded = base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
#                 if mime == "text/html":
#                     decoded = BeautifulSoup(decoded, "html.parser").get_text(separator="\n", strip=True)
#                 body_text += decoded + "\n"
#                 return

#             # Multipart
#             if mime.startswith("multipart") and "parts" in part:
#                 for p in part["parts"]:
#                     walk(p)

#         walk(payload)
#         return body_text.strip(), attachments

#     def _parse_ts(self, ts):
#         if "(UTC)" in ts:
#             ts = ts.replace("(UTC)", "").strip()
#         try:
#             return parser.parse(ts)
#         except:
#             return datetime.utcnow()

#     def fetch_messages(
#         self, 
#         tenant_id, 
#         query=None, 
#         max_results=10, 
#         filters=None,
#         mark_as_read=True,
#         is_manual_mode=False
#     ):
#         """
#         Fetch Gmail messages.

#         Core behavior preserved.
#         Fix: Do NOT mark more emails than we actually return.
#         """
#         from Tools.GmailTool import GmailTool

#         creds = self.get_credentials(tenant_id)

#         gmail_tool = GmailTool(tenant_id=tenant_id, auth_mode="auto")
#         gmail_tool.creds = creds
#         gmail_tool.authenticate()

#         # Build query using filter system
#         # if filters:
#         #     query, extra_args = self.build_query(filters, is_manual_mode=is_manual_mode)
#         #     logger.warning(f"[FILTERS] Gmail API Filters → {filters}")
#         #     logger.warning(f"[QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Query → {query}")
#         # else:
#         #     extra_args = {}
#         query, extra_args = self.build_query(filters or {}, is_manual_mode=is_manual_mode)

#         logger.debug(f"[GMAIL_SERVICE] Using SEARCH: {query}")

#         # Ensure label exists BEFORE fetching messages (AUTO mode only)
#         label_id = None
#         if mark_as_read and not is_manual_mode:
#             try:
#                 label_id = gmail_tool.ensure_label_exists("processed_by_agentic")
#                 logger.debug(f"[AUTO_MODE] Label 'processed_by_agentic' ready: {label_id}")
#             except Exception as e:
#                 logger.error(f"[AUTO_MODE] Failed to ensure label exists: {e}")
#                 mark_as_read = False

#         # Fetch more than needed to compensate for Gmail inconsistencies
#         resp = gmail_tool.list_messages(
#             query=query,
#             max_results=max_results * 3,
#             **extra_args
#         )

#         raw_messages = resp.get("messages", []) or []
#         final_messages = []

#         labeled_count = 0
#         failed_count = 0

#         for msg in raw_messages:
#             # ✅ HARD STOP: do not process more than max_results
#             if len(final_messages) >= max_results:
#                 break

#             msg_id = msg.get("id")
#             if not msg_id:
#                 continue

#             detail = gmail_tool.get_message(msg_id)
#             if "error" in detail:
#                 logger.error(f"[GMAIL_SERVICE] Failed to fetch full message {msg_id}: {detail['error']}")
#                 continue

#             full = self._extract_message(detail)

#             # AUTO mode → mark read + label ONLY for messages we return
#             if mark_as_read and not is_manual_mode and label_id:
#                 try:
#                     gmail_tool.modify_message_labels(
#                         message_id=msg_id,
#                         labels_to_add=[label_id],
#                         labels_to_remove=["UNREAD"]
#                     )
#                     labeled_count += 1
#                     logger.debug(f"[AUTO_MODE] Marked message {msg_id} as read and labeled")
#                 except AttributeError as ae:
#                     logger.error(f"[AUTO_MODE] Method 'modify_message_labels' not found: {ae}")
#                     failed_count += 1
#                     continue
#                 except Exception as e:
#                     logger.warning(f"[AUTO_MODE] Failed to mark message {msg_id}: {e}")
#                     failed_count += 1
#                     continue

#             # Manual mode OR successful AUTO mode
#             final_messages.append(full)

#         # Log labeling statistics
#         if not is_manual_mode and (labeled_count > 0 or failed_count > 0):
#             logger.info(f"[AUTO_MODE] Labeling stats: {labeled_count} succeeded, {failed_count} failed")
#             if failed_count > 0:
#                 logger.warning(f"[AUTO_MODE] {failed_count} messages excluded to prevent reprocessing")

#         # Sort by timestamp descending (unchanged)
#         final_messages.sort(
#             key=lambda x: self._parse_ts(x["timestamp"]),
#             reverse=True
#         )

#         logger.info(
#             f"[GMAIL_SERVICE] Returning {len(final_messages)} message(s) | "
#             f"Mode={'MANUAL' if is_manual_mode else 'AUTO'}"
#         )

#         return final_messages




















# class GmailService:

#     def get_credentials(self, tenant_id: int):
#         """Fetch and normalize OAuth credentials."""
#         url = f"{langgraph_urls.GMAIL_CREDENTIALS_URL}?tenant_id={tenant_id}"
#         logger.debug(f"[GMAIL_SERVICE] Fetching credentials -> {url}")

#         try:
#             resp = requests.get(url, timeout=10)
#         except requests.ConnectionError as e:
#             raise Exception(
#                 f"[GMAIL_SERVICE] Connection failed to credential endpoint ({url}). "
#                 f"Error: {e}. "
#                 f"Ensure bot-builder-service is running and accessible."
#             )
#         except requests.Timeout as e:
#             raise Exception(
#                 f"[GMAIL_SERVICE] Credential endpoint timeout ({url}). "
#                 f"Service took too long to respond. Error: {e}"
#             )
#         except Exception as e:
#             raise Exception(
#                 f"[GMAIL_SERVICE] Failed to fetch credentials from {url}. Error: {e}"
#             )

#         if resp.status_code != 200:
#             error_detail = resp.text[:500] if resp.text else "No error details"
#             raise Exception(
#                 f"[GMAIL_SERVICE] Credential API failed with status {resp.status_code}. "
#                 f"Endpoint: {url} | Response: {error_detail}"
#             )

#         creds_json = resp.json().get("credentials")

#         if not creds_json:
#             raise Exception(
#                 f"[GMAIL_SERVICE] Missing 'credentials' in response from {url}. "
#                 f"Verify tenant_id={tenant_id} has valid Gmail credentials configured."
#             )

#         # Normalize token object
#         normalized = {
#             "token": creds_json.get("access_token") or creds_json.get("token"),
#             "refresh_token": creds_json.get("refresh_token"),
#             "token_uri": creds_json.get("token_uri"),
#             "client_id": creds_json.get("client_id"),
#             "client_secret": creds_json.get("client_secret"),
#             "scopes": creds_json.get("scopes", ["https://mail.google.com/"])
#         }

#         creds = Credentials(**normalized)

#         # Auto refresh token if expired
#         if creds.expired and creds.refresh_token:
#             try:
#                 creds.refresh(Request())
#                 logger.info("[GMAIL_SERVICE] Token refreshed successfully")
#             except Exception as e:
#                 logger.error(f"[GMAIL_SERVICE] Token refresh failed: {e}")

#         return creds

#     def build_query(self, filters: dict, is_manual_mode: bool = False) -> tuple[str, dict]:
#         """
#         Convert UI filters to Gmail API query.
        
#         Args:
#             filters: Filter dictionary from UI
#             is_manual_mode: If True (manual execution), override readStatus to 'unread'
#                            but respect ALL other filters (sender, subject, labels, etc.)
#         """
#         q_parts = []
#         api_params = {}

#         # If no filters -> default unread inbox
#         if not filters:
#             return "in:inbox is:unread", {}

#         # ✅ Free search text - ALWAYS RESPECT
#         if filters.get("q"):
#             q_parts.append(filters["q"])

#         # ✅ Sender filter - ALWAYS RESPECT
#         if filters.get("sender"):
#             senders = [s.strip() for s in filters["sender"].split(",")]
#             if len(senders) > 1:
#                 q_parts.append("(" + " OR ".join([f"from:({s})" for s in senders]) + ")")
#             else:
#                 q_parts.append(f"from:({senders[0]})")

#         # ✅ Subject filter - ALWAYS RESPECT
#         if filters.get("subject"):
#             q_parts.append(f'subject:"{filters["subject"]}"')

#         # ⚠️ Read status logic - OVERRIDE IN MANUAL MODE
#         read_status = filters.get("readStatus")
        
#         if is_manual_mode:
#             # ✅ MANUAL MODE: FORCE unread, ignore user's readStatus setting
#             logger.info("[MANUAL_MODE] Overriding readStatus filter to 'unread' (other filters preserved)")
#             q_parts.append("is:unread")
#         else:
#             # ✅ AUTO MODE: Respect user's readStatus choice
#             if read_status == "read":
#                 q_parts.append("-is:unread")
#             elif read_status == "all":
#                 pass  # Fetch all
#             else:
#                 q_parts.append("is:unread")  # Default unread
        
#         # ✅ Exclude already processed emails (AUTO mode only)
#         if not is_manual_mode:
#             q_parts.append("-label:processed_by_agentic")

#         # ✅ Drafts - ALWAYS RESPECT
#         if filters.get("includeDrafts"):
#             q_parts.append("in:drafts")

#         # ✅ Spam/Trash - ALWAYS RESPECT
#         if filters.get("includeSpamTrash"):
#             api_params["includeSpamTrash"] = True

#         # ✅ Labels - ALWAYS RESPECT
#         if filters.get("labelIds"):
#             api_params["labelIds"] = filters["labelIds"]

#         # Build final query
#         final_query = " ".join(q_parts).strip()

#         if not final_query:
#             final_query = "in:inbox is:unread"

#         # Ensure inbox exists if not overridden
#         if "in:" not in final_query:
#             final_query = f"in:inbox {final_query}"

#         logger.debug(f"[BUILD_QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Final Query: {final_query}")
#         return final_query, api_params

#     def _extract_message(self, msg_detail: dict) -> dict:
#         """Extract body and attachments from Gmail API response."""
#         payload = msg_detail.get("payload", {})
#         headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

#         body_text, attachments = self._extract_body_and_attachments(payload)

#         return {
#             "message_id": msg_detail.get("id"),
#             "thread_id": msg_detail.get("threadId"),
#             "from": headers.get("From"),
#             "to": headers.get("To"),
#             "subject": headers.get("Subject"),
#             "timestamp": headers.get("Date") or datetime.utcnow().isoformat(),
#             "body_text": body_text,
#             "attachments": attachments,
#         }

#     def _extract_body_and_attachments(self, payload):
#         """Extract clean text + attachments."""
#         body_text = ""
#         attachments = []

#         def walk(part):
#             nonlocal body_text, attachments

#             mime = part.get("mimeType", "")
#             filename = part.get("filename", "")
#             body = part.get("body", {})
#             data = body.get("data")

#             # Attachments
#             if filename and mime not in ("text/plain", "text/html"):
#                 attachments.append({
#                     "filename": filename,
#                     "mimetype": mime
#                 })
#                 return

#             # Body Data
#             if data:
#                 decoded = base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
#                 if mime == "text/html":
#                     decoded = BeautifulSoup(decoded, "html.parser").get_text(separator="\n", strip=True)
#                 body_text += decoded + "\n"
#                 return

#             # Multipart
#             if mime.startswith("multipart") and "parts" in part:
#                 for p in part["parts"]:
#                     walk(p)

#         walk(payload)
#         return body_text.strip(), attachments

#     def _parse_ts(self, ts):
#         if "(UTC)" in ts:
#             ts = ts.replace("(UTC)", "").strip()
#         try:
#             return parser.parse(ts)
#         except:
#             return datetime.utcnow()
        
#     def fetch_messages(
#         self, 
#         tenant_id, 
#         query=None, 
#         max_results=10, 
#         filters=None,
#         mark_as_read=True,
#         is_manual_mode=False
#     ):
#         """
#         Fetch Gmail messages.

#         Core behavior preserved.
#         Fix: Do NOT mark more emails than we actually return.
#         """
#         from Tools.GmailTool import GmailTool

#         creds = self.get_credentials(tenant_id)

#         gmail_tool = GmailTool(tenant_id=tenant_id, auth_mode="auto")
#         gmail_tool.creds = creds
#         gmail_tool.authenticate()

#         # Build query using filter system
#         # if filters:
#         #     query, extra_args = self.build_query(filters, is_manual_mode=is_manual_mode)
#         #     logger.warning(f"[FILTERS] Gmail API Filters → {filters}")
#         #     logger.warning(f"[QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Query → {query}")
#         # else:
#         #     extra_args = {}
#         query, extra_args = self.build_query(filters or {}, is_manual_mode=is_manual_mode)

#         logger.debug(f"[GMAIL_SERVICE] Using SEARCH: {query}")

#         # Ensure label exists BEFORE fetching messages (AUTO mode only)
#         label_id = None
#         if mark_as_read and not is_manual_mode:
#             try:
#                 label_id = gmail_tool.ensure_label_exists("processed_by_agentic")
#                 logger.debug(f"[AUTO_MODE] Label 'processed_by_agentic' ready: {label_id}")
#             except Exception as e:
#                 logger.error(f"[AUTO_MODE] Failed to ensure label exists: {e}")
#                 mark_as_read = False

#         # Fetch more than needed to compensate for Gmail inconsistencies
#         resp = gmail_tool.list_messages(
#             query=query,
#             max_results=max_results * 3,
#             **extra_args
#         )

#         raw_messages = resp.get("messages", []) or []
#         final_messages = []

#         labeled_count = 0
#         failed_count = 0

#         for msg in raw_messages:
#             # ✅ HARD STOP: do not process more than max_results
#             if len(final_messages) >= max_results:
#                 break

#             msg_id = msg.get("id")
#             if not msg_id:
#                 continue

#             detail = gmail_tool.get_message(msg_id)
#             if "error" in detail:
#                 logger.error(f"[GMAIL_SERVICE] Failed to fetch full message {msg_id}: {detail['error']}")
#                 continue

#             full = self._extract_message(detail)

#             # AUTO mode → mark read + label ONLY for messages we return
#             if mark_as_read and not is_manual_mode and label_id:
#                 try:
#                     gmail_tool.modify_message_labels(
#                         message_id=msg_id,
#                         labels_to_add=[label_id],
#                         labels_to_remove=["UNREAD"]
#                     )
#                     labeled_count += 1
#                     logger.debug(f"[AUTO_MODE] Marked message {msg_id} as read and labeled")
#                 except AttributeError as ae:
#                     logger.error(f"[AUTO_MODE] Method 'modify_message_labels' not found: {ae}")
#                     failed_count += 1
#                     continue
#                 except Exception as e:
#                     logger.warning(f"[AUTO_MODE] Failed to mark message {msg_id}: {e}")
#                     failed_count += 1
#                     continue

#             # Manual mode OR successful AUTO mode
#             final_messages.append(full)

#         # Log labeling statistics
#         if not is_manual_mode and (labeled_count > 0 or failed_count > 0):
#             logger.info(f"[AUTO_MODE] Labeling stats: {labeled_count} succeeded, {failed_count} failed")
#             if failed_count > 0:
#                 logger.warning(f"[AUTO_MODE] {failed_count} messages excluded to prevent reprocessing")

#         # Sort by timestamp descending (unchanged)
#         final_messages.sort(
#             key=lambda x: self._parse_ts(x["timestamp"]),
#             reverse=True
#         )

#         logger.info(
#             f"[GMAIL_SERVICE] Returning {len(final_messages)} message(s) | "
#             f"Mode={'MANUAL' if is_manual_mode else 'AUTO'}"
#         )

#         return final_messages
















    #lasted Code  
    # def fetch_messages(
    #     self, 
    #     tenant_id, 
    #     query=None, 
    #     max_results=10, 
    #     filters=None,
    #     mark_as_read=True,
    #     is_manual_mode=False
    # ):
    #     """
    #     Fetch Gmail messages.
        
    #     Args:
    #         tenant_id: Tenant ID for authentication
    #         query: Gmail search query string
    #         max_results: Maximum number of results to return
    #         filters: Filter dictionary from UI
    #         mark_as_read: Optional. If True, mark emails as read and add label (AUTO mode)
    #                     If False, don't modify emails (MANUAL mode). Default: True
    #         is_manual_mode: Optional. If True, force unread filter regardless of user settings.
    #                     If False, respect user's readStatus filter. Default: False
    #     """
    #     from Tools.GmailTool import GmailTool

    #     creds = self.get_credentials(tenant_id)

    #     gmail_tool = GmailTool(tenant_id=tenant_id, auth_mode="auto")
    #     gmail_tool.creds = creds
    #     gmail_tool.authenticate()

    #     # Build query using filter system
    #     if filters:
    #         query, extra_args = self.build_query(filters, is_manual_mode=is_manual_mode)
    #         logger.warning(f"[FILTERS] Gmail API Filters → {filters}")
    #         logger.warning(f"[QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Query → {query}")
    #     else:
    #         extra_args = {}
        
    #     logger.debug(f"[GMAIL_SERVICE] Using SEARCH: {query}")
        
    #     # ✅ Ensure label exists BEFORE fetching messages (AUTO mode only)
    #     label_id = None
    #     if mark_as_read and not is_manual_mode:
    #         try:
    #             label_id = gmail_tool.ensure_label_exists("processed_by_agentic")
    #             logger.debug(f"[AUTO_MODE] Label 'processed_by_agentic' ready: {label_id}")
    #         except Exception as e:
    #             logger.error(f"[AUTO_MODE] Failed to ensure label exists: {e}")
    #             # Continue without labeling if label creation fails
    #             mark_as_read = False
        
    #     resp = gmail_tool.list_messages(
    #         query=query,
    #         max_results=max_results * 3,
    #         **extra_args
    #     )

    #     raw_messages = resp.get("messages", []) or []
    #     final_messages = []
        
    #     # Track labeling success
    #     labeled_count = 0
    #     failed_count = 0

    #     for msg in raw_messages:
    #         msg_id = msg.get("id")
    #         if not msg_id:
    #             continue

    #         detail = gmail_tool.get_message(msg_id)

    #         if "error" in detail:
    #             logger.error(f"[GMAIL_SERVICE] Failed to fetch full message {msg_id}: {detail['error']}")
    #             continue

    #         full = self._extract_message(detail)
            
    #         # ✅ Mark as read and add label ONLY in AUTO mode
    #         if mark_as_read and not is_manual_mode and label_id:
    #             try:
    #                 # Mark as read AND add processed label in ONE call
    #                 gmail_tool.modify_message_labels(
    #                     message_id=msg_id,
    #                     labels_to_add=[label_id],
    #                     labels_to_remove=["UNREAD"]
    #                 )
                    
    #                 labeled_count += 1
    #                 logger.debug(f"[AUTO_MODE] Marked message {msg_id} as read and labeled")
                    
    #                 # Only add successfully labeled messages to results
    #                 final_messages.append(full)
                    
    #             except AttributeError as ae:
    #                 logger.error(f"[AUTO_MODE] Method 'modify_message_labels' not found: {ae}")
    #                 failed_count += 1
    #                 # CRITICAL: Don't add this message to avoid reprocessing
    #                 continue
    #             except Exception as e:
    #                 logger.warning(f"[AUTO_MODE] Failed to mark message {msg_id}: {e}")
    #                 failed_count += 1
    #                 # Don't add this message to results if we couldn't mark it
    #                 continue
    #         else:
    #             # Manual mode - add all messages without marking
    #             final_messages.append(full)

    #     # Log labeling statistics (AUTO mode)
    #     if not is_manual_mode and (labeled_count > 0 or failed_count > 0):
    #         logger.info(f"[AUTO_MODE] Labeling stats: {labeled_count} succeeded, {failed_count} failed")
    #         if failed_count > 0:
    #             logger.warning(f"[AUTO_MODE] {failed_count} messages excluded to prevent reprocessing")

    #     # Sort by timestamp descending
    #     final_messages.sort(
    #         key=lambda x: self._parse_ts(x["timestamp"]),
    #         reverse=True
    #     )
        
    #     # Limit to requested count
    #     final_messages = final_messages[:max_results]

    #     logger.info(f"[GMAIL_SERVICE] Returning {len(final_messages)} message(s) | Mode={'MANUAL' if is_manual_mode else 'AUTO'}")
    #     return final_messages










class GmailService:

    def get_credentials(self, tenant_id: int):
        """Fetch and normalize OAuth credentials."""
        url = f"{langgraph_urls.GMAIL_CREDENTIALS_URL}?tenant_id={tenant_id}"
        logger.debug(f"[GMAIL_SERVICE] Fetching credentials -> {url}")

        resp = requests.get(url)

        if resp.status_code != 200:
            raise Exception(f"[GMAIL_SERVICE] Credential API failed: {resp.text}")

        creds_json = resp.json().get("credentials")

        if not creds_json:
            raise Exception("[GMAIL_SERVICE] Missing credentials JSON")

        # # Normalize token object
        # normalized = {
        #     "token": creds_json.get("access_token") or creds_json.get("token"),
        #     "refresh_token": creds_json.get("refresh_token"),
        #     "token_uri": creds_json.get("token_uri"),
        #     "client_id": creds_json.get("client_id"),
        #     "client_secret": creds_json.get("client_secret"),
        #     "scopes": creds_json.get("scopes", ["https://mail.google.com/"])
        # }
        token_value = (
            creds_json.get("token")
            or creds_json.get("access_token")
            or creds_json.get("accessToken")
            or creds_json.get("oauth_token")
        )

        if not token_value:
            raise Exception(f"[GMAIL_SERVICE] token field missing for tenant_id={tenant_id}")

        normalized = {
            "token": token_value,
            "refresh_token": creds_json.get("refresh_token") or creds_json.get("refreshToken"),
            "token_uri": creds_json.get("token_uri") or "https://oauth2.googleapis.com/token",
            "client_id": creds_json.get("client_id"),
            "client_secret": creds_json.get("client_secret"),
            "scopes": creds_json.get("scopes", ["https://mail.google.com/"]),
        }
        creds = Credentials(**normalized)

        # Auto refresh token if expired
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("[GMAIL_SERVICE] Token refreshed successfully")
            except Exception as e:
                logger.error(f"[GMAIL_SERVICE] Token refresh failed: {e}")

        return creds

    def build_query(self, filters: dict, is_manual_mode: bool = False) -> tuple[str, dict]:
        """
        Convert UI filters to Gmail API query.
        
        Args:
            filters: Filter dictionary from UI
            is_manual_mode: If True (manual execution), override readStatus to 'unread'
                           but respect ALL other filters (sender, subject, labels, etc.)
        """
        q_parts = []
        api_params = {}

        # If no filters -> default unread inbox
        if not filters:
            return "in:inbox is:unread", {}

        # ✅ Free search text - ALWAYS RESPECT
        if filters.get("q"):
            q_parts.append(filters["q"])

        # ✅ Sender filter - ALWAYS RESPECT
        if filters.get("sender"):
            senders = [s.strip() for s in filters["sender"].split(",")]
            if len(senders) > 1:
                q_parts.append("(" + " OR ".join([f"from:({s})" for s in senders]) + ")")
            else:
                q_parts.append(f"from:({senders[0]})")

        # ✅ Subject filter - ALWAYS RESPECT
        if filters.get("subject"):
            q_parts.append(f'subject:"{filters["subject"]}"')

        # ⚠️ Read status logic - OVERRIDE IN MANUAL MODE
        read_status = filters.get("readStatus")
        
        if is_manual_mode:
            # ✅ MANUAL MODE: FORCE unread, ignore user's readStatus setting
            logger.info("[MANUAL_MODE] Overriding readStatus filter to 'unread' (other filters preserved)")
            q_parts.append("is:unread")
        else:
            # ✅ AUTO MODE: Respect user's readStatus choice
            if read_status == "read":
                q_parts.append("-is:unread")
            elif read_status == "all":
                pass  # Fetch all
            else:
                q_parts.append("is:unread")  # Default unread
        
        # ✅ Exclude already processed emails (AUTO mode only)
        if not is_manual_mode:
            q_parts.append("-label:processed_by_agentic")

        # ✅ Drafts - ALWAYS RESPECT
        if filters.get("includeDrafts"):
            q_parts.append("in:drafts")

        # ✅ Spam/Trash - ALWAYS RESPECT
        if filters.get("includeSpamTrash"):
            api_params["includeSpamTrash"] = True

        # ✅ Labels - ALWAYS RESPECT
        if filters.get("labelIds"):
            api_params["labelIds"] = filters["labelIds"]

        # Build final query
        final_query = " ".join(q_parts).strip()

        if not final_query:
            final_query = "in:inbox is:unread"

        # Ensure inbox exists if not overridden
        if "in:" not in final_query:
            final_query = f"in:inbox {final_query}"

        logger.debug(f"[BUILD_QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Final Query: {final_query}")
        return final_query, api_params

    def _extract_message(self, msg_detail: dict) -> dict:
        """Extract body and attachments from Gmail API response."""
        payload = msg_detail.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

        body_text, attachments = self._extract_body_and_attachments(payload)

        return {
            "message_id": msg_detail.get("id"),
            "thread_id": msg_detail.get("threadId"),
            "from": headers.get("From"),
            "to": headers.get("To"),
            "subject": headers.get("Subject"),
            "timestamp": headers.get("Date") or datetime.utcnow().isoformat(),
            "body_text": body_text,
            "attachments": attachments,
        }

    def _extract_body_and_attachments(self, payload):
        """Extract clean text + attachments."""
        body_text = ""
        attachments = []

        def walk(part):
            nonlocal body_text, attachments

            mime = part.get("mimeType", "")
            filename = part.get("filename", "")
            body = part.get("body", {})
            data = body.get("data")

            # Attachments
            if filename and mime not in ("text/plain", "text/html"):
                attachments.append({
                    "filename": filename,
                    "mimetype": mime
                })
                return

            # Body Data
            if data:
                decoded = base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
                if mime == "text/html":
                    decoded = BeautifulSoup(decoded, "html.parser").get_text(separator="\n", strip=True)
                body_text += decoded + "\n"
                return

            # Multipart
            if mime.startswith("multipart") and "parts" in part:
                for p in part["parts"]:
                    walk(p)

        walk(payload)
        return body_text.strip(), attachments

    def _parse_ts(self, ts):
        if "(UTC)" in ts:
            ts = ts.replace("(UTC)", "").strip()
        try:
            return parser.parse(ts)
        except:
            return datetime.utcnow()
        
    def fetch_messages(
        self, 
        tenant_id, 
        query=None, 
        max_results=10, 
        filters=None,
        mark_as_read=True,
        is_manual_mode=False
    ):
        """
        Fetch Gmail messages.

        Core behavior preserved.
        Fix: Do NOT mark more emails than we actually return.
        """
        from Tools.GmailTool import GmailTool

        creds = self.get_credentials(tenant_id)

        gmail_tool = GmailTool(tenant_id=tenant_id, auth_mode="auto")
        gmail_tool.creds = creds
        gmail_tool.authenticate()

        # Build query using filter system
        # if filters:
        #     query, extra_args = self.build_query(filters, is_manual_mode=is_manual_mode)
        #     logger.warning(f"[FILTERS] Gmail API Filters → {filters}")
        #     logger.warning(f"[QUERY] Mode={'MANUAL' if is_manual_mode else 'AUTO'}, Query → {query}")
        # else:
        #     extra_args = {}
        query, extra_args = self.build_query(filters or {}, is_manual_mode=is_manual_mode)

        logger.debug(f"[GMAIL_SERVICE] Using SEARCH: {query}")

        # Ensure label exists BEFORE fetching messages (AUTO mode only)
        label_id = None
        if mark_as_read and not is_manual_mode:
            try:
                label_id = gmail_tool.ensure_label_exists("processed_by_agentic")
                logger.debug(f"[AUTO_MODE] Label 'processed_by_agentic' ready: {label_id}")
            except Exception as e:
                logger.error(f"[AUTO_MODE] Failed to ensure label exists: {e}")
                mark_as_read = False

        # Fetch more than needed to compensate for Gmail inconsistencies
        resp = gmail_tool.list_messages(
            query=query,
            max_results=max_results * 3,
            **extra_args
        )

        raw_messages = resp.get("messages", []) or []
        final_messages = []

        labeled_count = 0
        failed_count = 0

        for msg in raw_messages:
            # ✅ HARD STOP: do not process more than max_results
            if len(final_messages) >= max_results:
                break

            msg_id = msg.get("id")
            if not msg_id:
                continue

            detail = gmail_tool.get_message(msg_id)
            if "error" in detail:
                logger.error(f"[GMAIL_SERVICE] Failed to fetch full message {msg_id}: {detail['error']}")
                continue

            full = self._extract_message(detail)

            # AUTO mode → mark read + label ONLY for messages we return
            if mark_as_read and not is_manual_mode and label_id:
                try:
                    gmail_tool.modify_message_labels(
                        message_id=msg_id,
                        labels_to_add=[label_id],
                        labels_to_remove=["UNREAD"]
                    )
                    labeled_count += 1
                    logger.debug(f"[AUTO_MODE] Marked message {msg_id} as read and labeled")
                except AttributeError as ae:
                    logger.error(f"[AUTO_MODE] Method 'modify_message_labels' not found: {ae}")
                    failed_count += 1
                    continue
                except Exception as e:
                    logger.warning(f"[AUTO_MODE] Failed to mark message {msg_id}: {e}")
                    failed_count += 1
                    continue

            # Manual mode OR successful AUTO mode
            final_messages.append(full)

        # Log labeling statistics
        if not is_manual_mode and (labeled_count > 0 or failed_count > 0):
            logger.info(f"[AUTO_MODE] Labeling stats: {labeled_count} succeeded, {failed_count} failed")
            if failed_count > 0:
                logger.warning(f"[AUTO_MODE] {failed_count} messages excluded to prevent reprocessing")

        # Sort by timestamp descending (unchanged)
        final_messages.sort(
            key=lambda x: self._parse_ts(x["timestamp"]),
            reverse=True
        )

        logger.info(
            f"[GMAIL_SERVICE] Returning {len(final_messages)} message(s) | "
            f"Mode={'MANUAL' if is_manual_mode else 'AUTO'}"
        )

        return final_messages
   