"""
Tools/GSheetsTool.py

GSheetsTool - lightweight helper for Google Sheets API operations
with safe credential handling, DB token persistence, and manual OAuth.
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from sqlalchemy.orm import Session
from app.models import ToolAuthorization
from app.database.DatabaseOperationPostgreSQL import db_session
from .BaseTool import BaseTool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GSheetsTool(BaseTool):
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",  # for profile email
    ]

    def __init__(
        self,
        tenant_id: int,
        credentials_file: str = "client_secret.json",
        auth_mode: str = "local",
        redirect_uri: Optional[str] = None,
        preloaded_creds: Optional[Credentials] = None,
    ):
        super().__init__(name="GSheets Tool", description="Read/write Google Sheets.")
        self.tenant_id = tenant_id
        self.credentials_file = credentials_file
        self.auth_mode = auth_mode
        self.redirect_uri = redirect_uri
        self.creds: Optional[Credentials] = preloaded_creds
        self.service = None
        self.authenticated_email: Optional[str] = None

    # ------------------- DB Token Persistence -------------------
    def _save_token(self, creds: Credentials) -> None:
        token_data = json.loads(creds.to_json())
        db_sess: Session = next(db_session())
        try:
            auth = (
                db_sess.query(ToolAuthorization)
                .filter_by(tenant_id=self.tenant_id, tool_name="gsheets")
                .first()
            )
            if auth:
                auth.token_json = token_data
                auth.del_flag = False
                auth.updated_at = datetime.utcnow()
            else:
                auth = ToolAuthorization(
                    tenant_id=self.tenant_id,
                    tool_name="gsheets",
                    token_json=token_data,
                    del_flag=False,
                )
                db_sess.add(auth)
            db_sess.commit()
        except Exception as e:
            db_sess.rollback()
            logger.error(f"Failed to save GSheets token: {e}")
        finally:
            db_sess.close()

    def _load_token(self) -> Optional[Credentials]:
        db_sess: Session = next(db_session())
        try:
            # Case-insensitive — DB may store "GSheets", "gsheets", or "Gsheets"
            auth = (
                db_sess.query(ToolAuthorization)
                .filter(
                    ToolAuthorization.tenant_id == self.tenant_id,
                    ToolAuthorization.tool_name.ilike("gsheets"),
                    ToolAuthorization.del_flag == False,
                )
                .first()
            )
            if auth and auth.token_json:
                return Credentials.from_authorized_user_info(auth.token_json, self.SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load GSheets token from DB: {e}")
        finally:
            db_sess.close()
        return None

    # ------------------- Authentication -------------------
    def authenticate(self) -> None:
        """
        Authenticate using:
          1. preloaded_creds (MCP injection)
          2. DB token (refresh if needed)
          3. OAuth flow (local or manual)
        """
        # 1. Pre-loaded credentials
        if self.creds is not None:
            if self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                    self._save_token(self.creds)
                except Exception:
                    logger.exception("Failed to refresh pre-loaded GSheets credentials")
                    raise
        else:
            # 2. Load from DB or run OAuth
            if not os.path.exists(self.credentials_file):
                raise FileNotFoundError(f"Credential file not found: {self.credentials_file}")

            self.creds = self._load_token()

            if not self.creds or not self.creds.valid:
                try:
                    if self.creds and self.creds.expired and self.creds.refresh_token:
                        self.creds.refresh(Request())
                        self._save_token(self.creds)
                    else:
                        if self.auth_mode == "local":
                            flow = Flow.from_client_secrets_file(
                                self.credentials_file,
                                scopes=self.SCOPES,
                            )
                            self.creds = flow.run_local_server(port=0)
                            self._save_token(self.creds)
                        elif self.auth_mode == "manual":
                            raise RuntimeError(
                                "Manual auth mode: call get_auth_url() and then handle_oauth_callback(code)."
                            )
                        else:
                            raise ValueError(f"Unknown auth_mode: {self.auth_mode}")
                except Exception:
                    logger.exception("GSheets authentication/refresh failed.")
                    raise

        # Build Sheets service
        self.service = build("sheets", "v4", credentials=self.creds, cache_discovery=False)

        # Optional: fetch authenticated email via Drive API
        try:
            drive_service = build("drive", "v3", credentials=self.creds, cache_discovery=False)
            about = drive_service.about().get(fields="user").execute()
            self.authenticated_email = about.get("user", {}).get("emailAddress")
        except Exception:
            self.authenticated_email = None

    # ------------------- Manual OAuth -------------------
    def get_auth_url(self, custom_state: Optional[str] = None) -> Tuple[str, str]:
        """Return (auth_url, state). State can carry context like 'mcp'."""
        if self.auth_mode != "manual":
            raise RuntimeError("get_auth_url() called but auth_mode != 'manual'")
        if not self.redirect_uri:
            raise ValueError("redirect_uri must be set for manual auth mode")

        flow = Flow.from_client_secrets_file(
            self.credentials_file,
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri,
        )

        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=custom_state,
        )
        return auth_url, state

    def handle_oauth_callback(self, code: str) -> Dict[str, Any]:
        """Exchange code → save token → build service."""
        if not self.redirect_uri:
            return {"error": "redirect_uri must be set"}

        try:
            flow = Flow.from_client_secrets_file(
                self.credentials_file,
                scopes=self.SCOPES,
                redirect_uri=self.redirect_uri,
            )
            flow.fetch_token(code=code)

            self.creds = flow.credentials
            self._save_token(self.creds)

            self.service = build("sheets", "v4", credentials=self.creds, cache_discovery=False)

            # Fetch email
            try:
                drive_service = build("drive", "v3", credentials=self.creds, cache_discovery=False)
                about = drive_service.about().get(fields="user").execute()
                self.authenticated_email = about.get("user", {}).get("emailAddress")
            except Exception:
                self.authenticated_email = None

            return {
                "message": "GSheets token saved and service ready.",
                "email": self.authenticated_email,
            }
        except Exception as e:
            logger.error("OAuth callback failed: %s", e, exc_info=True)
            return {"error": str(e)}

    # ------------------- Core Sheet Operations -------------------
    def read_sheet(self, spreadsheet_id: str, range_name: str) -> Dict[str, Any]:
        try:
            self.authenticate()
            result = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=range_name)
                .execute()
            )
            values = result.get("values", [])
            return {"data": values, "range": range_name}
        except HttpError as error:
            logger.error("Sheets API error: %s", error)
            return {"error": str(error)}
        except Exception as e:
            logger.exception("Unexpected error reading sheet")
            return {"error": str(e)}

    def write_sheet(
        self, spreadsheet_id: str, range_name: str, values: List[List[Any]]
    ) -> Dict[str, Any]:
        try:
            self.authenticate()
            body = {"values": values}
            result = (
                self.service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption="RAW",
                    body=body,
                )
                .execute()
            )
            return {"updatedCells": result.get("updatedCells"), "range": range_name}
        except HttpError as error:
            logger.error("Sheets API error: %s", error)
            return {"error": str(error)}
        except Exception as e:
            logger.exception("Unexpected error writing sheet")
            return {"error": str(e)}

    def append_rows(
        self, spreadsheet_id: str, range_name: str, values: List[List[Any]]
    ) -> Dict[str, Any]:
        try:
            self.authenticate()
            body = {"values": values}
            result = (
                self.service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                )
                .execute()
            )
            return {"updates": result.get("updates"), "range": range_name}
        except HttpError as error:
            logger.error("Sheets API error: %s", error)
            return {"error": str(error)}
        except Exception as e:
            logger.exception("Unexpected error appending rows")
            return {"error": str(e)}

    def clear_sheet(self, spreadsheet_id: str, range_name: str) -> Dict[str, Any]:
        try:
            self.authenticate()
            result = (
                self.service.spreadsheets()
                .values()
                .clear(spreadsheetId=spreadsheet_id, range=range_name, body={})
                .execute()
            )
            return {"clearedRange": result.get("clearedRange")}
        except HttpError as error:
            logger.error("Sheets API error: %s", error)
            return {"error": str(error)}
        except Exception as e:
            logger.exception("Unexpected error clearing sheet")
            return {"error": str(e)}