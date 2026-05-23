import os
import logging
import requests
from email.message import EmailMessage
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from engine.export_strategies.base import IExportStrategy
from engine.export_strategies.factory import ExportStrategyFactory
from Tools.GmailTool import GmailTool
from engine import langgraph_urls
import uuid 
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CREDENTIALS_URL = langgraph_urls.GMAIL_CREDENTIALS_URL

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# def resolve_attachment_path(path):
#     """
#     Ensures attachment paths always become:
#     /home/ubuntu/<rest_of_path>

#     Handles:
#     - already absolute paths
#     - relative paths such as: mcp_bot_builder/attachments/<id>/file.pdf
#     """

#     BASE_PREFIX = "/home/ubuntu"

#     # ✅ If the path is already absolute:
#     if os.path.isabs(path):
#         # Ensure it starts with /home/ubuntu
#         if not path.startswith(BASE_PREFIX):
#             return os.path.join(BASE_PREFIX, os.path.basename(path))
#         return path

#     # ✅ For relative paths: prefix with /home/ubuntu/
#     abs_path = os.path.join(BASE_PREFIX, path)

#     # Normalize path
#     abs_path = os.path.abspath(abs_path)

#     if not os.path.exists(abs_path):
#         raise FileNotFoundError(f"Attachment not found: {abs_path}")

#     return abs_path


# @ExportStrategyFactory.register("Gmail")
# class GmailExportStrategy(IExportStrategy):

#     def __init__(self):
#         self.creds = None

#     def _fetch_credentials(self, tenant_id: str, jwt_token: str = None) -> Credentials:
#         """Fetch credentials from API and refresh if expired"""
#         logger.debug(f"[GMAIL_FETCH_CREDS] tenant_id={tenant_id}")

#         if not jwt_token:
#             logger.error("[GMAIL_FETCH_CREDS] Missing JWT token")
#             raise ValueError("JWT token required to fetch Gmail credentials")

#         headers = {"Authorization": f"Bearer {jwt_token}"}
#         resp = requests.get(CREDENTIALS_URL, headers=headers)

#         if resp.status_code != 200:
#             logger.error(f"[GMAIL_FETCH_CREDS] Failed (status={resp.status_code}): {resp.text}")
#             raise Exception(f"Failed to fetch credentials: {resp.text}")
            
#         payload = resp.json()
        
#         # Create credentials object (FIX: read from credentials root)
#         creds_data = payload.get("credentials", {})
        
#         creds = Credentials(
#             token=creds_data.get("access_token"),
#             refresh_token=creds_data.get("refresh_token"),
#             token_uri=creds_data.get("token_uri"),
#             client_id=creds_data.get("client_id"),
#             client_secret=creds_data.get("client_secret"),
#             scopes=creds_data.get("scopes", ["https://www.googleapis.com/auth/gmail.send"])
#         )


#         # ✅ CHECK IF TOKEN IS EXPIRED AND REFRESH
#         if creds and creds.expired and creds.refresh_token:
#             logger.info("[GMAIL_FETCH_CREDS] Token expired, attempting refresh...")
#             try:
#                 creds.refresh(Request())
#                 logger.info("[GMAIL_FETCH_CREDS] Token refreshed successfully")
                
#                 # ✅ SAVE REFRESHED TOKEN BACK TO DATABASE
#                 self._save_refreshed_token(tenant_id, jwt_token, creds)
                
#             except Exception as e:
#                 logger.error(f"[GMAIL_FETCH_CREDS] Token refresh failed: {e}")
#                 raise Exception(f"Failed to refresh expired token: {e}")

#         return creds

#     def _save_refreshed_token(self, tenant_id: str, jwt_token: str, creds: Credentials):
#         """Save refreshed token back to database"""
#         try:
#             update_url = CREDENTIALS_URL  # Or use a dedicated update endpoint
#             headers = {"Authorization": f"Bearer {jwt_token}"}
            
#             updated_token_data = {
#                 "access_token": creds.token,
#                 "refresh_token": creds.refresh_token,
#                 "token_uri": creds.token_uri,
#                 "client_id": creds.client_id,
#                 "client_secret": creds.client_secret,
#                 "scopes": creds.scopes
#             }
            
#             # You'll need to implement a PUT/PATCH endpoint for this
#             resp = requests.put(update_url, headers=headers, json=updated_token_data)
            
#             if resp.status_code == 200:
#                 logger.info("[GMAIL_SAVE_TOKEN] Refreshed token saved to database")
#             else:
#                 logger.warning(f"[GMAIL_SAVE_TOKEN] Failed to save: {resp.text}")
                
#         except Exception as e:
#             logger.error(f"[GMAIL_SAVE_TOKEN] Error saving token: {e}")

    
#     def _build_email_message(self, form_data: dict) -> EmailMessage:
#         logger.debug("[GMAIL_BUILD_MSG] Building email message")
    
#         msg = EmailMessage()
#         msg["To"] = form_data.get("to")
#         msg["Subject"] = form_data.get("subject", "No Subject")
#         msg.set_content(form_data.get("body", ""))
    
#         attachments = form_data.get("attachments", [])
#         logger.debug(f"[GMAIL_BUILD_MSG] Total attachments: {len(attachments)}")
    
#         for file_path in attachments:
#             try:
#                 # ✅ Convert relative → absolute path
#                 resolved = resolve_attachment_path(file_path)
#                 logger.debug(f"[GMAIL_BUILD_MSG] Resolved path: {resolved}")
    
#                 if not os.path.exists(resolved):
#                     logger.warning(f"[GMAIL_BUILD_MSG] Attachment not found even after resolve: {resolved}")
#                     continue
    
#                 with open(resolved, "rb") as f:
#                     file_data = f.read()
#                     file_name = os.path.basename(resolved)
    
#                     import mimetypes
#                     mime_type, _ = mimetypes.guess_type(resolved)
#                     main_type, sub_type = (mime_type or "application/octet-stream").split("/", 1)
    
#                     msg.add_attachment(
#                         file_data,
#                         maintype=main_type,
#                         subtype=sub_type,
#                         filename=file_name,
#                     )
#                     logger.debug(f"[GMAIL_BUILD_MSG] Attached file: {file_name}")
    
#             except Exception as e:
#                 logger.error(f"[GMAIL_BUILD_MSG] Failed to attach {file_path}: {e}")
    
#         logger.debug("[GMAIL_BUILD_MSG] Email message prepared successfully")
#         return msg

#     def send(self, tenant_id: str, form_data: dict, jwt: str) -> dict:
#         trace_id = uuid.uuid4().hex[:10]
#         logger.info(f"[GMAIL_EXPORT_START][{trace_id}] Export started for tenant={tenant_id}")

#         try:
#             # Fetch and auto-refresh credentials
#             logger.debug(f"[GMAIL_EXPORT][{trace_id}] Fetching credentials...")
#             self.creds = self._fetch_credentials(tenant_id, jwt)

#             # Authenticate Gmail Tool
#             logger.debug(f"[GMAIL_EXPORT][{trace_id}] Authenticating Gmail tool...")
#             gmail_tool = GmailTool(tenant_id=tenant_id, auth_mode="manual")
#             gmail_tool.creds = self.creds
#             gmail_tool.authenticate()

#             # Send Email
#             logger.debug(f"[GMAIL_EXPORT][{trace_id}] Sending email to={form_data.get('to')}")
#             # response = gmail_tool.send_email(
#             #     to=form_data.get("to"),
#             #     subject=form_data.get("subject"),
#             #     body=form_data.get("body"),
#             #     attachments=form_data.get("attachments", []),
#             # )
#             # ✅ Resolve all attachment paths
#             resolved_attachments = []
#             for p in form_data.get("attachments", []):
#                 try:
#                     resolved = resolve_attachment_path(p)
#                     resolved_attachments.append(resolved)
#                 except Exception as e:
#                     logger.error(f"[GMAIL_EXPORT][{trace_id}] Cannot resolve attachment {p}: {e}")
            
#             # ✅ Send the resolved absolute paths to GmailTool
#             response = gmail_tool.send_email(
#                 to=form_data.get("to"),
#                 subject=form_data.get("subject"),
#                 body=form_data.get("body"),
#                 attachments=resolved_attachments,
#             )


#             logger.info(f"[GMAIL_EXPORT_END][{trace_id}] Gmail export completed successfully")

#             return {
#                 "status": "success",
#                 "channel": "gmail",
#                 "to": form_data.get("to"),
#                 "subject": form_data.get("subject"),
#                 "attachments": form_data.get("attachments", []),
#                 "response": response,
#             }

#         except Exception as ex:
#             logger.error(f"[GMAIL_EXPORT_ERROR][{trace_id}] {ex}", exc_info=True)
#             return {
#                 "status": "error",
#                 "channel": "gmail",
#                 "error": str(ex),
#             }


def resolve_attachment_path(path):
    """
    Ensures attachment paths always become:
    /home/ubuntu/<rest_of_path>

    Handles:
    - already absolute paths
    - relative paths such as: mcp_bot_builder/attachments/<id>/file.pdf
    """

    BASE_PREFIX = ""

    # ✅ If the path is already absolute:
    if os.path.isabs(path):
        # Ensure it starts with /home/ubuntu
        if not path.startswith(BASE_PREFIX):
            return os.path.join(BASE_PREFIX, os.path.basename(path))
        return path

    # ✅ For relative paths: prefix with /home/ubuntu/
    abs_path = os.path.join(BASE_PREFIX, path)

    # Normalize path
    abs_path = os.path.abspath(abs_path)

    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Attachment not found: {abs_path}")

    return abs_path


@ExportStrategyFactory.register("Gmail")
class GmailExportStrategy(IExportStrategy):

    def __init__(self):
        self.creds = None
        self.context = None  # Added to allow optional context resolution

    # ✅ New helper for resolving dot-paths
    def _resolve_dot_path(self, path, context=None):
        """Resolve dot path like previousNode.output.result.attachments.0 if context provided"""
        if not context or not isinstance(path, str) or "." not in path:
            return path

        try:
            parts = path.split(".")
            value = context
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                elif isinstance(value, list) and part.isdigit():
                    value = value[int(part)]
                else:
                    return path
            return value
        except Exception as e:
            logger.warning(f"[GMAIL_DOT_PATH] Failed to resolve '{path}': {e}")
            return path

    def _fetch_credentials(self, tenant_id: str, jwt_token: str = None) -> Credentials:
        """Fetch credentials from API and refresh if expired"""
        logger.debug(f"[GMAIL_FETCH_CREDS] tenant_id={tenant_id}")

        if not jwt_token:
            logger.error("[GMAIL_FETCH_CREDS] Missing JWT token")
            raise ValueError("JWT token required to fetch Gmail credentials")

        headers = {"Authorization": f"Bearer {jwt_token}"}
        resp = requests.get(CREDENTIALS_URL, headers=headers)

        if resp.status_code != 200:
            logger.error(f"[GMAIL_FETCH_CREDS] Failed (status={resp.status_code}): {resp.text}")
            raise Exception(f"Failed to fetch credentials: {resp.text}")

        payload = resp.json()

        creds_data = payload.get("credentials", {})

        creds = Credentials(
            token=creds_data.get("access_token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri"),
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
            scopes=creds_data.get("scopes", ["https://www.googleapis.com/auth/gmail.send"])
        )

        # ✅ Check if token expired and refresh
        if creds and creds.expired and creds.refresh_token:
            logger.info("[GMAIL_FETCH_CREDS] Token expired, attempting refresh...")
            try:
                creds.refresh(Request())
                logger.info("[GMAIL_FETCH_CREDS] Token refreshed successfully")
                self._save_refreshed_token(tenant_id, jwt_token, creds)
            except Exception as e:
                logger.error(f"[GMAIL_FETCH_CREDS] Token refresh failed: {e}")
                raise Exception(f"Failed to refresh expired token: {e}")

        return creds

    def _save_refreshed_token(self, tenant_id: str, jwt_token: str, creds: Credentials):
        """Save refreshed token back to database"""
        try:
            update_url = CREDENTIALS_URL  # Or use a dedicated update endpoint
            headers = {"Authorization": f"Bearer {jwt_token}"}

            updated_token_data = {
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": creds.scopes
            }

            resp = requests.put(update_url, headers=headers, json=updated_token_data)

            if resp.status_code == 200:
                logger.info("[GMAIL_SAVE_TOKEN] Refreshed token saved to database")
            else:
                logger.warning(f"[GMAIL_SAVE_TOKEN] Failed to save: {resp.text}")

        except Exception as e:
            logger.error(f"[GMAIL_SAVE_TOKEN] Error saving token: {e}")

    def _build_email_message(self, form_data: dict) -> EmailMessage:
        logger.debug("[GMAIL_BUILD_MSG] Building email message")

        msg = EmailMessage()
        msg["To"] = form_data.get("to")
        msg["Subject"] = form_data.get("subject", "No Subject")
        msg.set_content(form_data.get("body", ""))

        attachments = form_data.get("attachments", [])
        logger.debug(f"[GMAIL_BUILD_MSG] Total attachments: {len(attachments)}")

        for file_path in attachments:
            try:
                resolved = resolve_attachment_path(file_path)
                logger.debug(f"[GMAIL_BUILD_MSG] Resolved path: {resolved}")

                if not os.path.exists(resolved):
                    logger.warning(f"[GMAIL_BUILD_MSG] Attachment not found even after resolve: {resolved}")
                    continue

                with open(resolved, "rb") as f:
                    file_data = f.read()
                    file_name = os.path.basename(resolved)

                    mime_type, _ = mimetypes.guess_type(resolved)
                    main_type, sub_type = (mime_type or "application/octet-stream").split("/", 1)

                    msg.add_attachment(
                        file_data,
                        maintype=main_type,
                        subtype=sub_type,
                        filename=file_name,
                    )
                    logger.debug(f"[GMAIL_BUILD_MSG] Attached file: {file_name}")

            except Exception as e:
                logger.error(f"[GMAIL_BUILD_MSG] Failed to attach {file_path}: {e}")

        logger.debug("[GMAIL_BUILD_MSG] Email message prepared successfully")
        return msg

    def send(self, tenant_id: str, form_data: dict, jwt: str) -> dict:
        trace_id = uuid.uuid4().hex[:10]
        logger.info(f"[GMAIL_EXPORT_START][{trace_id}] Export started for tenant={tenant_id}")

        try:
            # Fetch and auto-refresh credentials
            logger.debug(f"[GMAIL_EXPORT][{trace_id}] Fetching credentials...")
            self.creds = self._fetch_credentials(tenant_id, jwt)

            # Authenticate Gmail Tool
            logger.debug(f"[GMAIL_EXPORT][{trace_id}] Authenticating Gmail tool...")
            gmail_tool = GmailTool(tenant_id=tenant_id, auth_mode="manual")
            gmail_tool.creds = self.creds
            gmail_tool.authenticate()

            # ✅ Resolve all attachment paths (supports dot-paths now)
            resolved_attachments = []
            context = getattr(self, "context", None)

            for p in form_data.get("attachments", []):
                try:
                    # Resolve dot-path if present
                    resolved_ref = self._resolve_dot_path(p, context)
                    resolved = resolve_attachment_path(resolved_ref)
                    resolved_attachments.append(resolved)
                except Exception as e:
                    logger.error(f"[GMAIL_EXPORT][{trace_id}] Cannot resolve attachment {p}: {e}")

            # ✅ Send the resolved absolute paths to GmailTool
            response = gmail_tool.send_email(
                to=form_data.get("to"),
                subject=form_data.get("subject"),
                body=form_data.get("body"),
                attachments=resolved_attachments,
            )

            logger.info(f"[GMAIL_EXPORT_END][{trace_id}] Gmail export completed successfully")

            return {
                "status": "success",
                "channel": "gmail",
                "to": form_data.get("to"),
                "subject": form_data.get("subject"),
                "attachments": form_data.get("attachments", []),
                "response": response,
            }

        except Exception as ex:
            logger.error(f"[GMAIL_EXPORT_ERROR][{trace_id}] {ex}", exc_info=True)
            return {
                "status": "error",
                "channel": "gmail",
                "error": str(ex),
            }
