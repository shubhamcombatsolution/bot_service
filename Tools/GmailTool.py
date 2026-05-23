"""
Tools/GmailTool.py

GmailTool - lightweight helper for Gmail API operations with safer handling
of credential id_token and authenticated email extraction.
"""

import os
import json
import tempfile
import base64
import logging
import mimetypes
from typing import List, Optional, Dict, Any, Tuple, Union
from google_auth_oauthlib.flow import Flow
from email.message import EmailMessage
from app.models import ToolAuthorization
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from app.database.DatabaseOperationPostgreSQL import db_session
from .BaseTool import BaseTool
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GmailTool(BaseTool):
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.readonly"
    ]

    def __init__(self, tenant_id: int,
                 credentials_file: str = "client_secret.json",
                 auth_mode: str = "local",
                 redirect_uri: Optional[str] = None,
                 preloaded_creds: Optional[Credentials] = None):
        super().__init__(name="Gmail Tool", description="Send/read/manage Gmail messages.")
        self.tenant_id = tenant_id
        self.credentials_file = credentials_file
        self.auth_mode = auth_mode
        self.redirect_uri = redirect_uri
        self.creds: Optional[Credentials] = None
        self.service = None
        self.flow: Optional[Flow] = None
        self.authenticated_email: Optional[str] = None
        self.creds: Optional[Credentials] = preloaded_creds 
    # ---------- DB Token Persistence ----------
    def _save_token(self, creds: Credentials) -> None:
        db_sess = next(db_session())
        token_data = json.loads(creds.to_json())
        try:
            auth = db_sess.query(ToolAuthorization).filter_by(
                tenant_id=self.tenant_id,
                tool_name="gmail"
            ).first()

            if auth:
                auth.token_json = token_data
                auth.del_flag = False
                auth.updated_at = datetime.utcnow()
            else:
                auth = ToolAuthorization(
                    tenant_id=self.tenant_id,
                    tool_name="gmail",
                    token_json=token_data,
                    del_flag=False
                )
                db_sess.add(auth)

            db_sess.commit()
        finally:
            db_sess.close()

    def _load_token(self) -> Optional[Credentials]:
        db_sess: Session = next(db_session())
        try:
            auth = db_sess.query(ToolAuthorization).filter_by(
                tenant_id=self.tenant_id,
                tool_name="gmail",
                del_flag=False
            ).first()
            if auth and auth.token_json:
                return Credentials.from_authorized_user_info(auth.token_json, self.SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load Gmail token from DB: {e}")
        finally:
            db_sess.close()
        return None

    


    def authenticate(self) -> None:

        # 1. Use preloaded creds ONLY if valid
        if self.creds is not None and getattr(self.creds, "token", None):
            logger.info("[GMAIL] Using preloaded credentials")

            if self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
                self._save_token(self.creds)

        else:
            logger.info("[GMAIL] Loading credentials from DB")

            # 2. Load from DB
            self.creds = self._load_token()

            if not self.creds:
                logger.warning(f"[GMAIL] No credentials found in DB for tenant_id {self.tenant_id}")
                return  # No creds, service will not be initialized

            # 3. Refresh if needed
            if self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
                self._save_token(self.creds)

        # 🔥 CRITICAL: Build Gmail service
        self.service = build("gmail", "v1", credentials=self.creds, cache_discovery=False)

        # 4. Fetch profile
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            self.authenticated_email = profile.get("emailAddress")
        except Exception:
            self.authenticated_email = None
                

    def get_auth_url(self, custom_state: Optional[str] = None) -> Tuple[str, str]:
        if self.auth_mode != "manual":
            raise RuntimeError("get_auth_url() called but auth_mode != 'manual'")
        if not self.redirect_uri:
            raise ValueError("redirect_uri must be set for manual auth mode")
    
        flow = Flow.from_client_secrets_file(
            self.credentials_file,
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri
        )
    
        # ✅ Pass custom state if provided
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=custom_state if custom_state else None
        )
    
        self.flow = flow
        return auth_url, state


    def handle_oauth_callback(self, code: str) -> Dict[str, Any]:
        if not self.redirect_uri:
            return {"error": "redirect_uri must be set"}
    
        try:
            # Create a fresh Flow object
            flow = Flow.from_client_secrets_file(
                self.credentials_file,
                scopes=self.SCOPES,
                redirect_uri=self.redirect_uri
            )
            flow.fetch_token(code=code)  # exchange code for credentials
    
            # Save creds
            self.creds = flow.credentials
            self._save_token(self.creds)
    
            # Build Gmail service
            self.service = build("gmail", "v1", credentials=self.creds, cache_discovery=False)
    
            # Get authenticated email
            profile = self.service.users().getProfile(userId="me").execute()
            self.authenticated_email = profile.get("emailAddress")
    
            return {
                "message": "Gmail token saved and service ready.",
                "email": self.authenticated_email
            }
    
        except Exception as e:
            logger.error("OAuth callback failed: %s", e, exc_info=True)
            return {"error": str(e)}

 
    # ---------- Recipient normalization ----------
    def _split_recipients(self, raw: str) -> List[str]:
        """
        Split recipient string on commas or semicolons and return cleaned parts.
        """
        if not raw:
            return []
        parts = []
        for part in raw.replace(";", ",").split(","):
            p = part.strip()
            if p:
                parts.append(p)
        return parts

    def _extract_emails(self, token: str) -> List[str]:
        """
        Return list of email addresses found in token (first-level extraction).
        """
        import re
        found = re.findall(r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})", token)
        return found

    def _normalize_recipients(self, to: Union[str, List[str]]) -> List[str]:
        """
        Normalize various shapes of recipient input and return a list of email addresses.
        Accepts:
          - "alice@example.com"
          - "To: alice@example.com"
          - "alice@example.com, bob@ex.com"
          - ["alice@example.com", "Bob <bob@ex.com>"]
        """
        addrs: List[str] = []

        items: List[str]
        if isinstance(to, list):
            items = [str(x).strip() for x in to if x]
        else:
            items = self._split_recipients(str(to))

        for item in items:
            if not item:
                continue
            # strip common header prefixes like 'To:'
            item_clean = item.strip()
            if item_clean.lower().startswith("to:"):
                item_clean = item_clean.split(":", 1)[1].strip()

            emails = self._extract_emails(item_clean)
            if emails:
                addrs.extend(emails)
            else:
                # Log non-email tokens for debugging (they will be skipped)
                logger.debug("Recipient token is not an email and will be skipped: %s", item_clean)

        # deduplicate while preserving order
        seen = set()
        out = []
        for e in addrs:
            if e not in seen:
                seen.add(e)
                out.append(e)
        return out

    # ---------- Message creation ----------
    def create_message(
        self,
        to: Union[str, List[str]],
        subject: str,
        body_text: str,
        html: bool = False,
        attachments: Optional[List[str]] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Create and return a dict with 'raw' base64url-encoded message suitable for Gmail API.
        """
        attachments = attachments or []

        # Normalize recipients
        valid_to = self._normalize_recipients(to)
        if not valid_to:
            raise ValueError(f"No valid recipient found in 'to' value: {to}")

        # Build EmailMessage
        em = EmailMessage()

        if html:
            em.add_alternative(body_text, subtype="html")
        else:
            em.set_content(body_text or "")

        em["To"] = ", ".join(valid_to)
        em["Subject"] = subject or ""

        # From header: prefer authenticated profile email; fallback to id_token extraction
        from_header = None
        if getattr(self, "authenticated_email", None):
            from_header = self.authenticated_email
        else:
            try:
                email_from_id = self._extract_email_from_id_token()
                if email_from_id:
                    from_header = email_from_id
            except Exception:
                logger.debug("Error extracting email from id_token; skipping From header.", exc_info=True)

        if from_header:
            em["From"] = from_header

        # CC/BCC
        if cc:
            cc_list = cc if isinstance(cc, list) else self._split_recipients(str(cc))
            cc_emails = self._normalize_recipients(cc_list)
            if cc_emails:
                em["Cc"] = ", ".join(cc_emails)
        if bcc:
            bcc_list = bcc if isinstance(bcc, list) else self._split_recipients(str(bcc))
            bcc_emails = self._normalize_recipients(bcc_list)
            if bcc_emails:
                em["Bcc"] = ", ".join(bcc_emails)

        if reply_to:
            em["Reply-To"] = reply_to

        # Attachments (use EmailMessage.add_attachment)
        for filepath in attachments:
            try:
                if not os.path.exists(filepath):
                    logger.warning("Attachment not found, skipping: %s", filepath)
                    continue
                ctype, encoding = mimetypes.guess_type(filepath)
                if ctype is None:
                    maintype, subtype = "application", "octet-stream"
                else:
                    maintype, subtype = ctype.split("/", 1)
                with open(filepath, "rb") as f:
                    file_data = f.read()
                em.add_attachment(file_data, maintype=maintype, subtype=subtype, filename=os.path.basename(filepath))
            except Exception:
                logger.exception("Failed to attach file: %s", filepath)

        # Debug log the MIME string (redact in prod if needed)
        try:
            mime_str = em.as_string()
            logger.debug("Prepared MIME message:\n%s", mime_str)
        except Exception:
            logger.debug("Could not render MIME as string for debug logging.", exc_info=True)

        raw_message = base64.urlsafe_b64encode(em.as_bytes()).decode()
        return {"raw": raw_message}

    # ---------- Gmail operations ----------
    def send_email(
        self,
        to: Union[str, List[str]],
        subject: str,
        body: str,
        html: bool = False,
        attachments: Optional[List[str]] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
        reply_to: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        try:
            self.authenticate()
            message = self.create_message(to, subject, body, html, attachments, cc, bcc, reply_to)
            if dry_run:
                logger.info("Dry run enabled. Message not sent.")
                return {"message": "Dry run successful", "raw": message["raw"]}

            sent_message = self.service.users().messages().send(userId="me", body=message).execute()

            from_addr = self.authenticated_email or self._extract_email_from_id_token() or "me"

            return {"message": f"Email sent successfully to {to}", "id": sent_message.get("id"), "from": from_addr, "raw_response": sent_message}
        except HttpError as error:
            err_str = str(error)
            try:
                details = getattr(error, "content", None) or getattr(error, "error_details", None)
                logger.error("Gmail API HttpError: %s ; details: %s", err_str, details)
            except Exception:
                logger.error("Gmail API HttpError: %s", err_str)
            return {"error": err_str}
        except Exception as e:
            logger.exception("Unexpected error sending email")
            return {"error": str(e)}

    # def list_messages(self, query: Optional[str] = None, max_results: int = 10, page_token: Optional[str] = None) -> Dict[str, Any]:
    #     try:
    #         self.authenticate()
    #         response = self.service.users().messages().list(userId="me", q=query, maxResults=max_results, pageToken=page_token).execute()
    #         messages = response.get("messages", []) or []
    #         results = []
    #         for msg in messages:
    #             try:
    #                 msg_detail = self.service.users().messages().get(userId="me", id=msg["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
    #                 results.append(msg_detail)
    #             except Exception as e:
    #                 logger.warning("Failed to fetch message %s: %s", msg.get("id"), e)
    #         return {"messages": results, "nextPageToken": response.get("nextPageToken")}
    #     except HttpError as error:
    #         logger.error("Gmail API error: %s", error)
    #         return {"error": str(error)}
    #     except Exception as e:
    #         logger.exception("Unexpected error listing emails")
    #         return {"error": str(e)}
    def list_messages(
        self,
        query: Optional[str] = None,
        max_results: int = 10,
        page_token: Optional[str] = None,
        label_ids: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Lists Gmail messages with optional filtering by query and labels.
        - Backward compatible: behaves exactly as before if label_ids is not passed.
        - label_ids: pass ['INBOX'] or any label list to restrict results.
        """
        try:
            self.authenticate()
    
            params = {
                "userId": "me",
                "maxResults": max_results,
            }
    
            if query:
                params["q"] = query
            if label_ids:  # ✅ only restrict when explicitly passed
                params["labelIds"] = label_ids
            if page_token:
                params["pageToken"] = page_token
    
            response = self.service.users().messages().list(**params).execute()
            messages = response.get("messages", []) or []
            results = []
    
            for msg in messages:
                try:
                    msg_detail = (
                        self.service.users()
                        .messages()
                        .get(
                            userId="me",
                            id=msg["id"],
                            format="metadata",
                            metadataHeaders=["From", "Subject", "Date"],
                        )
                        .execute()
                    )
                    # ✅ Skip non-inbox messages to avoid All Mail results
                    # if "INBOX" not in msg_detail.get("labelIds", []):
                    #     logger.debug(f"Skipping non-INBOX message: {msg['id']}")
                    #     continue
                    results.append(msg_detail)
                except Exception as e:
                    logger.warning("Failed to fetch message %s: %s", msg.get("id"), e)
    
            return {
                "messages": results,
                "nextPageToken": response.get("nextPageToken"),
            }
    
        except HttpError as error:
            logger.error("Gmail API error: %s", error)
            return {"error": str(error)}
        except Exception as e:
            logger.exception("Unexpected error listing emails")
            return {"error": str(e)}

    def get_message(self, message_id: str) -> Dict[str, Any]:
        try:
            self.authenticate()
            message = self.service.users().messages().get(userId="me", id=message_id, format="full").execute()
            return message
        except HttpError as error:
            logger.error("Gmail API error: %s", error)
            return {"error": str(error)}
        except Exception as e:
            logger.exception("Unexpected error fetching email")
            return {"error": str(e)}

    def modify_message_labels(self, message_id: str, labels_to_add: Optional[List[str]] = None, labels_to_remove: Optional[List[str]] = None) -> Dict[str, Any]:
        try:
            self.authenticate()
            body: Dict[str, Any] = {}
            if labels_to_add:
                body["addLabelIds"] = labels_to_add
            if labels_to_remove:
                body["removeLabelIds"] = labels_to_remove
            response = self.service.users().messages().modify(userId="me", id=message_id, body=body).execute()
            return response
        except HttpError as error:
            logger.error("Gmail API error: %s", error)
            return {"error": str(error)}
        except Exception as e:
            logger.exception("Unexpected error modifying labels")
            return {"error": str(e)}

    def mark_as_read(self, message_id: str) -> Dict[str, Any]:
        return self.modify_message_labels(message_id, labels_to_remove=["UNREAD"])

    def mark_as_unread(self, message_id: str) -> Dict[str, Any]:
        return self.modify_message_labels(message_id, labels_to_add=["UNREAD"])

    def list_labels(self) -> Dict[str, Any]:
        try:
            self.authenticate()
            response = self.service.users().labels().list(userId="me").execute()
            labels = response.get("labels", [])
            return {"labels": labels}
        except HttpError as error:
            logger.error("Gmail API error: %s", error)
            return {"error": str(error)}
        except Exception as e:
            logger.exception("Unexpected error listing labels")
            return {"error": str(e)}

    
    def ensure_label_exists(self, label_name: str) -> str:
        """Creates label if missing, returns its API label ID."""
        self.authenticate()

        # Fetch all existing labels
        labels = self.service.users().labels().list(userId="me").execute().get("labels", [])

        # Check if already exists
        for label in labels:
            if label["name"].lower() == label_name.lower():
                return label["id"]

        # Create new label
        label_body = {
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show"
        }

        new_label = self.service.users().labels().create(userId="me", body=label_body).execute()
        return new_label["id"]

# # Tools/GmailTool.py
# import pickle
# import os
# from google_auth_oauthlib.flow import Flow
# from googleapiclient.discovery import build

# class GmailTool:
#     def __init__(self, credentials_file="client_secret.json", token_file="gmail_token.pkl", redirect_uri=None):
#         self.credentials_file = credentials_file
#         self.token_file = token_file
#         self.redirect_uri = redirect_uri
#         self.scopes = [
#             "https://www.googleapis.com/auth/gmail.readonly",
#             "https://www.googleapis.com/auth/gmail.send",
#             "https://www.googleapis.com/auth/gmail.labels",
#             "https://www.googleapis.com/auth/gmail.modify"
#         ]
#         self.creds = None
#         self.service = None
#         self.flow = None
#         self.load_credentials()

#     def load_credentials(self):
#         if os.path.exists(self.token_file):
#             with open(self.token_file, "rb") as f:
#                 self.creds = pickle.load(f)
#         if self.creds:
#             self.service = build("gmail", "v1", credentials=self.creds)

#     def save_credentials(self):
#         with open(self.token_file, "wb") as f:
#             pickle.dump(self.creds, f)

#     def get_auth_url(self):
#         # Use Flow (Web Server OAuth)
#         flow = Flow.from_client_secrets_file(
#             self.credentials_file,
#             scopes=self.scopes,
#             redirect_uri=self.redirect_uri  # ✅ here, pass once in Flow
#         )
#         auth_url, state = flow.authorization_url(
#             access_type='offline',
#             include_granted_scopes='true',
#             prompt='consent'
#         )
#         self.flow = flow
#         return auth_url, state

#     def exchange_code(self, code):
#         # Exchange code using the same Flow object
#         self.flow.fetch_token(code=code)
#         self.creds = self.flow.credentials
#         self.save_credentials()
#         self.service = build("gmail", "v1", credentials=self.creds)
#         return self.creds

#     # Example Gmail APIs
#     def list_labels(self, user_id="me"):
#         if not self.service:
#             raise Exception("Gmail service not initialized")
#         results = self.service.users().labels().list(userId=user_id).execute()
#         return results.get("labels", [])
