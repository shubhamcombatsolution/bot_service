"""
Tools/HubSpotTool.py

HubSpotTool - complete OAuth + CRM helper modeled exactly after GmailTool.
"""

import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple, Any

from app.models import ToolAuthorization
from app.database.DatabaseOperationPostgreSQL import db_session
from .BaseTool import BaseTool

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class HubSpotTool(BaseTool):

    # AUTH_URL = "https://app.hubspot.com/oauth/authorize"
    AUTH_URL = "https://app-na2.hubspot.com/oauth/authorize"
    TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
    API_BASE = "https://api.hubapi.com"

    SCOPES = [
        "oauth",
        "crm.objects.contacts.read",
        "crm.objects.contacts.write",
        "crm.objects.companies.read",
        "crm.objects.companies.write",
        "crm.objects.deals.read",
        "crm.objects.deals.write",
        "crm.objects.custom.read",
        "crm.objects.custom.write",
        "crm.objects.orders.read",
        "crm.objects.orders.write",
        "crm.objects.owners.read",
    ]
    

    def __init__(
        self,
        tenant_id: int,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        auth_mode="manual",
        preloaded_creds: Optional[Dict] = None,
    ):
        super().__init__(
            name="HubSpot Tool",
            description="Access HubSpot CRM (contacts, companies, deals)."
        )
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_mode = auth_mode

        # Format of creds:
        # {
        #   "access_token": "...",
        #   "refresh_token": "...",
        #   "expires_at": <timestamp>,
        # }
        self.creds = preloaded_creds

    # ----------------------------------------------------
    # DB Persistence
    # ----------------------------------------------------
    def _save_token(self, token_json: Dict[str, Any]):
        db = next(db_session())
        try:
            auth = (
                db.query(ToolAuthorization)
                .filter_by(tenant_id=self.tenant_id, tool_name="hubspot")
                .first()
            )

            if auth:
                auth.token_json = token_json
                auth.del_flag = False
                auth.updated_at = datetime.utcnow()
            else:
                auth = ToolAuthorization(
                    tenant_id=self.tenant_id,
                    tool_name="hubspot",
                    token_json=token_json,
                    del_flag=False,
                )
                db.add(auth)

            db.commit()
        finally:
            db.close()

    def _load_token(self) -> Optional[Dict[str, Any]]:
        db = next(db_session())
        try:
            auth = (
                db.query(ToolAuthorization)
                .filter_by(tenant_id=self.tenant_id, tool_name="hubspot", del_flag=False)
                .first()
            )
            if auth:
                return auth.token_json
        finally:
            db.close()
        return None

    # ----------------------------------------------------
    # Authentication
    # ----------------------------------------------------
    def authenticate(self):
        """
        Ensure we have a valid access_token (refresh if needed).
        """

        # 1. Preloaded credentials from API call
        if self.creds:
            if self._is_expired(self.creds):
                self._refresh_token()
            return

        # 2. Load from DB
        token = self._load_token()
        if token:
            self.creds = token
            if self._is_expired(token):
                self._refresh_token()
            return

        # 3. No creds available → manual auth required
        if self.auth_mode == "manual":
            raise RuntimeError("Manual OAuth required. Call get_auth_url() first.")
        else:
            raise RuntimeError("Unsupported auth mode for HubSpot.")

    def _is_expired(self, token_json: Dict[str, Any]) -> bool:
        exp = token_json.get("expires_at")
        if not exp:
            return True
        return datetime.utcnow().timestamp() >= exp

    def _refresh_token(self):
        if not self.creds or "refresh_token" not in self.creds:
            raise RuntimeError("No refresh token available for HubSpot.")

        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.creds["refresh_token"],
        }

        r = requests.post(self.TOKEN_URL, data=data)
        if r.status_code != 200:
            raise RuntimeError(f"HubSpot refresh token failed: {r.text}")

        token_data = r.json()

        new_creds = {
            "access_token": token_data["access_token"],
            "refresh_token": self.creds["refresh_token"],  # HubSpot does NOT return refresh_token every time
            "expires_at": (datetime.utcnow() + timedelta(seconds=token_data["expires_in"])).timestamp(),
        }

        self.creds = new_creds
        self._save_token(new_creds)

    # ----------------------------------------------------
    # OAuth (Manual Web Flow)
    # ----------------------------------------------------
    def get_auth_url(self, custom_state: Optional[str] = None) -> Tuple[str, str]:
        """
        Create HubSpot authorization URL like GmailTool.get_auth_url.
        """
        if self.auth_mode != "manual":
            raise RuntimeError("get_auth_url() called but auth_mode != 'manual'")

        state = custom_state or "local"

        scope_string = "%20".join(self.SCOPES)

        auth_url = (
            f"{self.AUTH_URL}"
            f"?client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&scope={scope_string}"
            f"&state={state}"
            f"&response_type=code"
        )

        return auth_url, state

    def handle_oauth_callback(self, code: str) -> Dict[str, Any]:
        """
        Exchange auth code for access token and save to DB.
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "code": code,
        }

        r = requests.post(self.TOKEN_URL, data=data)
        if r.status_code != 200:
            return {"error": r.text}

        token_data = r.json()

        creds = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": (
                datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
            ).timestamp(),
        }

        self.creds = creds
        self._save_token(creds)

        return {
            "message": "HubSpot token saved successfully.",
            "scopes": self.SCOPES,
        }

    # ----------------------------------------------------
    # API Helpers
    # ----------------------------------------------------
    def _headers(self):
        self.authenticate()
        return {"Authorization": f"Bearer {self.creds['access_token']}"}

    # ----------------------------------------------------
    # API Methods — Contacts / Companies / Deals
    # ----------------------------------------------------
    def get_contacts(self, limit=10, after=None):
        url = f"{self.API_BASE}/crm/v3/objects/contacts"
        params = {"limit": limit}
        if after:
            params["after"] = after

        r = requests.get(url, headers=self._headers(), params=params)
        return r.json()

    def create_contact(self, email: str, first_name="", last_name=""):
        url = f"{self.API_BASE}/crm/v3/objects/contacts"
        payload = {
            "properties": {
                "email": email,
                "firstname": first_name,
                "lastname": last_name,
            }
        }

        r = requests.post(url, headers=self._headers(), json=payload)
        return r.json()

    def get_contact(self, contact_id: str):
        url = f"{self.API_BASE}/crm/v3/objects/contacts/{contact_id}"
        r = requests.get(url, headers=self._headers())
        return r.json()

    def search_contacts(self, email: str):
        url = f"{self.API_BASE}/crm/v3/objects/contacts/search"
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {"propertyName": "email", "operator": "EQ", "value": email}
                    ]
                }
            ]
        }
        r = requests.post(url, headers=self._headers(), json=payload)
        return r.json()
