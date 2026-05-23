"""
Tools/CalendarTool.py

CalendarTool – lightweight helper for Google Calendar API.
Supports:
  • Manual OAuth (web-server flow) with state preservation
  • Pre-loaded Credentials (MCP/API injection)
  • Token persistence per tenant in ToolAuthorization
"""

import os
import json
import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple, Union

from zoneinfo import ZoneInfo
from dateutil import parser as date_parser  # pip install python-dateutil

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from sqlalchemy.orm import Session
from app.models import ToolAuthorization
from app.database.DatabaseOperationPostgreSQL import db_session
from .BaseTool import BaseTool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CalendarTool(BaseTool):
    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    def __init__(
        self,
        tenant_id: int,
        credentials_file: str = "client_secret.json",
        auth_mode: str = "local",
        redirect_uri: Optional[str] = None,
        preloaded_creds: Optional[Credentials] = None,
    ):
        super().__init__(name="Calendar Tool", description="Read/write Google Calendar events.")
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
                .filter_by(tenant_id=self.tenant_id, tool_name="Calendar")
                .first()
            )
            if auth:
                auth.token_json = token_data
                auth.del_flag = False
                auth.updated_at = datetime.utcnow()
            else:
                auth = ToolAuthorization(
                    tenant_id=self.tenant_id,
                    tool_name="Calendar",
                    token_json=token_data,
                    del_flag=False,
                )
                db_sess.add(auth)
            db_sess.commit()
        finally:
            db_sess.close()

    def _load_token(self) -> Optional[Credentials]:
        db_sess: Session = next(db_session())
        try:
            auth = (
                db_sess.query(ToolAuthorization)
                .filter_by(
                    tenant_id=self.tenant_id,
                    tool_name="Calendar",
                    del_flag=False,
                )
                .first()
            )
            if auth and auth.token_json:
                return Credentials.from_authorized_user_info(auth.token_json, self.SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load Calendar token from DB: {e}")
        finally:
            db_sess.close()
        return None

    # ------------------- Authentication -------------------
    def authenticate(self):

        if self.creds is not None:
            if self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
                self._save_token(self.creds)

        else:
            self.creds = self._load_token()

            if not self.creds:
                raise RuntimeError("CALENDAR_AUTH_REQUIRED")

            if self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
                self._save_token(self.creds)

        self.service = build("calendar", "v3", credentials=self.creds, cache_discovery=False)

        # Optional: fetch authenticated email (useful for logging)
        try:
            profile = self.service.calendars().get(calendarId="primary").execute()
            self.authenticated_email = profile.get("id")
        except Exception:
            self.authenticated_email = None

    # ------------------- Manual OAuth -------------------
    def get_auth_url(self, custom_state: Optional[str] = None) -> Tuple[str, str]:
        """Return (auth_url, state).  State can carry context (e.g. 'mcp')."""
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
        """Exchange code → credentials → DB + service."""
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

            self.service = build("calendar", "v3", credentials=self.creds, cache_discovery=False)

            # fetch primary calendar email for logging
            profile = self.service.calendars().get(calendarId="primary").execute()
            self.authenticated_email = profile.get("id")

            return {
                "message": "Calendar token saved and service ready.",
                "email": self.authenticated_email,
            }
        except Exception as e:
            logger.error("OAuth callback failed: %s", e, exc_info=True)
            return {"error": str(e)}

    # ------------------- Helper: datetime parsing -------------------

    def _parse_datetime(self, dt_str: str, tz_name: str) -> datetime:
        dt_str = dt_str.strip().lower()

        now = datetime.now(ZoneInfo(tz_name))

        # 🔥 handle "today"
        if "today" in dt_str:
            time_part = dt_str.replace("today", "").strip()
            parsed_time = date_parser.parse(time_part)
            dt = now.replace(hour=parsed_time.hour, minute=parsed_time.minute, second=0, microsecond=0)

        # 🔥 handle "tomorrow"
        elif "tomorrow" in dt_str:
            time_part = dt_str.replace("tomorrow", "").strip()
            parsed_time = date_parser.parse(time_part)
            dt = (now + timedelta(days=1)).replace(
                hour=parsed_time.hour,
                minute=parsed_time.minute,
                second=0,
                microsecond=0
            )

        else:
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except:
                dt = date_parser.parse(dt_str)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(tz_name))

        return dt
        
    def _combine_date_and_time(
        self, date_str: str, time_str: str, tz_name: str = "Asia/Kolkata"
    ) -> datetime:
        """Combine YYYY-MM-DD + HH:MM (or 9:30 PM) → tz-aware datetime."""
        base = datetime.strptime(date_str.strip(), "%Y-%m-%d")
        try:
            parsed = date_parser.parse(time_str)
            hour, minute = parsed.hour, parsed.minute
        except Exception:
            hour, minute = map(int, time_str.split(":"))
        tz = ZoneInfo(tz_name)
        return datetime(
            year=base.year,
            month=base.month,
            day=base.day,
            hour=hour,
            minute=minute,
            tzinfo=tz,
        )

    # ------------------- Calendar Operations -------------------
    def book_appointment(
        self,
        title: str,
        location: str,
        description: str,
        start_time_str: Optional[str] = None,
        duration: float = 1.0,
        attendees: Optional[List[str]] = None,
        time_zone: str = "Asia/Kolkata",
        date: Optional[str] = None,
        time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an event. Accepts start_time_str OR (date+time)."""
        try:
            self.authenticate()

            # ---- resolve start datetime ----
            if start_time_str:
                if len(start_time_str.strip()) == 10 and time:
                    start_dt = self._combine_date_and_time(start_time_str.strip(), time, time_zone)
                else:
                    start_dt = self._parse_datetime(start_time_str, time_zone)
            elif date:
                if not time:
                    start_dt = self._parse_datetime(date, time_zone).replace(
                        hour=9, minute=0, second=0, microsecond=0
                    )
                else:
                    start_dt = self._combine_date_and_time(date, time, time_zone)
            else:
                return {"error": "Missing start_time_str or (date + time)."}

            if duration <= 0:
                return {"error": "Duration must be > 0."}

            end_dt = start_dt + timedelta(hours=duration)

            attendee_objs = []
            if attendees:
                for email in attendees:
                    email = (email or "").strip()
                    if "@" in email:
                        attendee_objs.append({"email": email})

            event = {
                "summary": title,
                "location": location,
                "description": description,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": time_zone},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": time_zone},
                "attendees": attendee_objs,
            }

            created = (
                self.service.events()
                .insert(calendarId="primary", body=event)
                .execute()
            )
            return {
                "message": "Event created.",
                "event_id": created.get("id"),
                "link": created.get("htmlLink"),
                "start": created.get("start"),
                "end": created.get("end"),
            }
        except HttpError as err:
            logger.error("Calendar API error: %s", err)
            return {"error": str(err)}
        except Exception as e:
            logger.exception("Unexpected error booking appointment")
            return {"error": str(e)}

    def list_events(
        self,
        max_results: int = 10,
        time_min: Optional[str] = None,
        time_zone: str = "UTC",
    ) -> List[Dict[str, Any]]:
        try:
            self.authenticate()
            now = datetime.utcnow().isoformat() + "Z" if not time_min else time_min
            events_result = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=now,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])
            out = []
            for ev in events:
                out.append(
                    {
                        "id": ev.get("id"),
                        "summary": ev.get("summary"),
                        "start": ev.get("start"),
                        "end": ev.get("end"),
                        "link": ev.get("htmlLink"),
                    }
                )
            return out or [{"message": "No upcoming events."}]
        except Exception as e:
            logger.error("Error listing events: %s", e)
            return [{"error": str(e)}]

    def get_event(self, event_id: str) -> Dict[str, Any]:
        try:
            self.authenticate()
            ev = self.service.events().get(calendarId="primary", eventId=event_id).execute()
            return {
                "id": ev.get("id"),
                "summary": ev.get("summary"),
                "location": ev.get("location"),
                "description": ev.get("description"),
                "start": ev.get("start"),
                "end": ev.get("end"),
                "attendees": ev.get("attendees"),
                "link": ev.get("htmlLink"),
            }
        except Exception as e:
            logger.error("Error getting event: %s", e)
            return {"error": str(e)}

    def update_event(self, event_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.authenticate()
            ev = self.service.events().get(calendarId="primary", eventId=event_id).execute()
            ev.update(updates)
            updated = (
                self.service.events()
                .update(calendarId="primary", eventId=event_id, body=ev)
                .execute()
            )
            return {"message": "Event updated.", "link": updated.get("htmlLink")}
        except Exception as e:
            logger.error("Error updating event: %s", e)
            return {"error": str(e)}

    def delete_event(self, event_id: str) -> Dict[str, Any]:
        try:
            self.authenticate()
            self.service.events().delete(calendarId="primary", eventId=event_id).execute()
            return {"message": f"Event {event_id} deleted."}
        except Exception as e:
            logger.error("Error deleting event: %s", e)
            return {"error": str(e)}

    def list_calendars(self) -> List[Dict[str, Any]]:
        try:
            self.authenticate()
            cl = self.service.calendarList().list().execute()
            return [
                {"id": c.get("id"), "summary": c.get("summary"), "timeZone": c.get("timeZone")}
                for c in cl.get("items", [])
            ]
        except Exception as e:
            logger.error("Error listing calendars: %s", e)
            return [{"error": str(e)}]

    def get_free_busy(
        self,
        time_min: str,
        time_max: str,
        time_zone: str = "Asia/Kolkata",
        calendar_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        try:
            self.authenticate()
            if calendar_ids is None:
                calendar_ids = ["primary"]
            tmin = self._parse_datetime(time_min, time_zone).isoformat()
            tmax = self._parse_datetime(time_max, time_zone).isoformat()
            body = {
                "timeMin": tmin,
                "timeMax": tmax,
                "timeZone": time_zone,
                "items": [{"id": cid} for cid in calendar_ids],
            }
            fb = self.service.freebusy().query(body=body).execute()
            return fb.get("calendars", {})
        except Exception as e:
            logger.error("Error getting free/busy: %s", e)
            return {"error": str(e)}