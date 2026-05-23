# import os
# from google_auth_oauthlib.flow import InstalledAppFlow
# from google.oauth2.credentials import Credentials
# from google.auth.transport.requests import Request
# from googleapiclient.discovery import build
# from datetime import datetime, timedelta
# from .BaseTool import BaseTool  # Assuming BaseTool is imported from the BaseTool file

# class CalendarTool(BaseTool):
#     SCOPES = ['https://www.googleapis.com/auth/calendar']
#     CLIENT_SECRET_FILE = 'client_secret.json'  # Path to your client_secret.json file

#     def __init__(self):
#         super().__init__(name="Google Calendar Tool", description="Book and manage Google Calendar events.")
#         self.creds = None
#         self.service = None

#     def authenticate(self):
#         """
#         Authenticate and initialize the Google Calendar API service.
#         """
#         if os.path.exists('token.json'):
#             self.creds = Credentials.from_authorized_user_file('token.json', self.SCOPES)

#         if not self.creds or not self.creds.valid:
#             if self.creds and self.creds.expired and self.creds.refresh_token:
#                 self.creds.refresh(Request())
#             else:
#                 raise Exception("Invalid or missing credentials. Please authenticate.")

#         self.service = build('calendar', 'v3', credentials=self.creds)

#     def get_auth_url(self):
#         """
#         Generate the Google authorization URL.
#         """
#         flow = InstalledAppFlow.from_client_secrets_file(self.CLIENT_SECRET_FILE, self.SCOPES)
#         flow.redirect_uri = 'https://127.0.0.1:8080/oauth2callback'
#         auth_url, _ = flow.authorization_url(prompt='consent')
#         return auth_url

#     def handle_oauth_callback(self, authorization_response):
#         """
#         Handle OAuth2 callback to retrieve and save credentials.
#         """
#         flow = InstalledAppFlow.from_client_secrets_file(self.CLIENT_SECRET_FILE, self.SCOPES)
#         flow.redirect_uri = 'https://127.0.0.1:8080/oauth2callback'
#         flow.fetch_token(authorization_response=authorization_response)
#         self.creds = flow.credentials

#         # Save the credentials for future use
#         with open('token.json', 'w') as token:
#             token.write(self.creds.to_json())

#         return "Authentication successful! You can now use the Calendar API."

#     def book_appointment(self, title, location, description, start_time_str, duration, attendees):
#         """
#         Book an appointment in Google Calendar.
#         """
#         self.authenticate()

#         # Parse the start time
#         print(start_time_str)
#         start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
#         end_time = start_time + timedelta(hours=duration)
#         print(start_time)
        
#         # Create event details
#         event_details = {
#             'summary': title,
#             'location': location,
#             'description': description,
#             'start': {
#                 'dateTime': start_time.isoformat(),
#                 'timeZone': 'Asia/Kolkata',
#             },
#             'end': {
#                 'dateTime': end_time.isoformat(),
#                 'timeZone': 'Asia/Kolkata',
#             },
#         }

#         print("OK")
#         # Add attendees if provided
#         if attendees:
#             event_details['attendees'] = [{'email': attendee} for attendee in attendees]
#         print("OsK")
        
#         # Schedule the event in Google Calendar
#         event = self.service.events().insert(calendarId='primary', body=event_details).execute()

#         return {
#             'message': f"Event '{event['summary']}' created successfully.",
#             'event_link': event.get('htmlLink')
#         }




# # import os
# # from google_auth_oauthlib.flow import InstalledAppFlow
# # from google.oauth2.credentials import Credentials
# # from google.auth.transport.requests import Request
# # from googleapiclient.discovery import build
# # from datetime import datetime, timedelta
# # from .BaseTool import BaseTool

# # class CalendarTool(BaseTool):
# #     SCOPES = ['https://www.googleapis.com/auth/calendar']

# #     def __init__(self, credentials_file='client_secret.json', token_file='token.json'):
# #         super().__init__(name="Google Calendar Tool", description="Book and manage Google Calendar events.")
# #         self.credentials_file = credentials_file  
# #         self.token_file = token_file
# #         self.creds = None
# #         self.service = None

# #     def authenticate(self):
# #         """
# #         Authenticate and initialize the Google Calendar API service.
# #         """
# #         if os.path.exists(self.token_file):
# #             self.creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)

# #         if not self.creds or not self.creds.valid:
# #             if self.creds and self.creds.expired and self.creds.refresh_token:
# #                 self.creds.refresh(Request())
# #             else:
# #                 flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
# #                 self.creds = flow.run_local_server(port=0)
# #                 with open(self.token_file, 'w') as token:
# #                     token.write(self.creds.to_json())

# #         self.service = build('calendar', 'v3', credentials=self.creds)

# #     def book_appointment(self, title, location, description, start_time_str, duration, attendees):
# #         """
# #         Book an appointment in Google Calendar.
# #         """
# #         self.authenticate()
# #         start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
# #         end_time = start_time + timedelta(hours=duration)

# #         event_details = {
# #             'summary': title,
# #             'location': location,
# #             'description': description,
# #             'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
# #             'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
# #         }

# #         if attendees:
# #             event_details['attendees'] = [{'email': attendee} for attendee in attendees]

# #         event = self.service.events().insert(calendarId='primary', body=event_details).execute()

# #         return {
# #             'message': f"Event '{event['summary']}' created successfully.",
# #             'event_link': event.get('htmlLink')
# #         }

# import os
# import logging
# from datetime import datetime, timedelta
# from google_auth_oauthlib.flow import InstalledAppFlow
# from google.oauth2.credentials import Credentials
# from google.auth.transport.requests import Request
# from googleapiclient.discovery import build
# from googleapiclient.errors import HttpError

# from langchain.tools import tool
# from .BaseTool import BaseTool  # Adjust import if needed

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# class CalendarTool(BaseTool):
#     SCOPES = ['https://www.googleapis.com/auth/calendar']

#     def __init__(self,
#                  credentials_file='/home/ubuntu/bot_builder/client_secret.json',
#                  token_file='/home/ubuntu/bot_builder/token.json',
#                  auth_mode='manual'):
#         super().__init__(name="Google Calendar Tool", description="Book and manage Google Calendar events.")
#         self.credentials_file = credentials_file
#         self.token_file = token_file
#         self.auth_mode = auth_mode
#         self.creds = None
#         self.service = None

#     def authenticate(self):
#         """Authenticate with Google Calendar API."""
#         if os.path.exists(self.token_file):
#             self.creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)

#         if not self.creds or not self.creds.valid:
#             if self.creds and self.creds.expired and self.creds.refresh_token:
#                 self.creds.refresh(Request())
#             else:
#                 if self.auth_mode == 'manual':
#                     flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#                     self.creds = flow.run_local_server(port=0)
#                     with open(self.token_file, 'w') as token:
#                         token.write(self.creds.to_json())
#                 else:
#                     raise Exception("Manual mode selected. Use get_auth_url() and handle_oauth_callback().")

#         self.service = build('calendar', 'v3', credentials=self.creds)

#     def get_auth_url(self):
#         """Return Google OAuth2 URL for manual authentication."""
#         flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#         flow.redirect_uri = 'https://jnanic.com/oauth2callback'
#         auth_url, _ = flow.authorization_url(prompt='consent')
#         return auth_url

#     def handle_oauth_callback(self, authorization_response):
#         """Handle OAuth2 callback and save credentials."""
#         flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#         flow.redirect_uri = 'https://jnanic.com/oauth2callback'
#         flow.fetch_token(authorization_response=authorization_response)
#         self.creds = flow.credentials
#         with open(self.token_file, 'w') as token:
#             token.write(self.creds.to_json())
#         self.service = build('calendar', 'v3', credentials=self.creds)
#         return "Authentication successful! You can now use the Calendar API."

#     @tool("book_appointment")
#     def book_appointment(self, title: str, location: str, description: str,
#                          start_time_str: str, duration: float, attendees: list = None) -> dict:
#         """Book a new calendar appointment."""
#         try:
#             self.authenticate()
#             start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
#             end_time = start_time + timedelta(hours=duration)

#             event_details = {
#                 'summary': title,
#                 'location': location,
#                 'description': description,
#                 'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
#                 'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
#                 'attendees': [{'email': email.strip()} for email in attendees] if attendees else []
#             }

#             event = self.service.events().insert(calendarId='primary', body=event_details).execute()
#             logger.info(f"Event created: {event.get('htmlLink')}")
#             return {'message': f"Event '{event['summary']}' created successfully.",
#                     'event_link': event.get('htmlLink')}

#         except HttpError as error:
#             logger.error(f"Google Calendar API error: {error}")
#             return {"error": str(error)}
#         except Exception as e:
#             logger.exception("Unexpected error")
#             return {"error": str(e)}

#     @tool("list_events")
#     def list_events(self, max_results=10):
#         """List upcoming events from the primary Google Calendar."""
#         try:
#             self.authenticate()
#             now = datetime.utcnow().isoformat() + 'Z'
#             events_result = self.service.events().list(
#                 calendarId='primary', timeMin=now,
#                 maxResults=max_results, singleEvents=True,
#                 orderBy='startTime'
#             ).execute()
#             events = events_result.get('items', [])
#             return events if events else "No upcoming events found."
#         except Exception as e:
#             logger.error(f"Error listing events: {e}")
#             return {"error": str(e)}
    

#     @tool("get_event")
#     def get_event(self, event_id: str):
#         """Get details of a specific event by ID."""
#         try:
#             self.authenticate()
#             event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
#             return event
#         except Exception as e:
#             logger.error(f"Error getting event: {e}")
#             return {"error": str(e)}

#     @tool("update_event")
#     def update_event(self, event_id: str, updates: dict):
#         """Update an existing event."""
#         try:
#             self.authenticate()
#             event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
#             event.update(updates)
#             updated_event = self.service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
#             return {"message": "Event updated successfully.", "event": updated_event}
#         except Exception as e:
#             logger.error(f"Error updating event: {e}")
#             return {"error": str(e)}

#     @tool("delete_event")
#     def delete_event(self, event_id: str):
#         """Delete an event by ID."""
#         try:
#             self.authenticate()
#             self.service.events().delete(calendarId='primary', eventId=event_id).execute()
#             return {"message": f"Event {event_id} deleted successfully."}
#         except Exception as e:
#             logger.error(f"Error deleting event: {e}")
#             return {"error": str(e)}

#     @tool("list_calendars")
#     def list_calendars(self):
#         """List all calendars."""
#         try:
#             self.authenticate()
#             calendar_list = self.service.calendarList().list().execute()
#             return calendar_list.get('items', [])
#         except Exception as e:
#             logger.error(f"Error listing calendars: {e}")
#             return {"error": str(e)}

#     @tool("get_free_busy")
#     def get_free_busy(self, time_min: str, time_max: str, time_zone: str = 'Asia/Kolkata', calendar_ids: list = None):
#         """Check free/busy info for calendars."""
#         try:
#             self.authenticate()
#             if calendar_ids is None:
#                 calendar_ids = ['primary']
#             body = {
#                 "timeMin": time_min,
#                 "timeMax": time_max,
#                 "timeZone": time_zone,
#                 "items": [{"id": cal_id} for cal_id in calendar_ids]
#             }
#             freebusy = self.service.freebusy().query(body=body).execute()
#             return freebusy.get('calendars', {})
#         except Exception as e:
#             logger.error(f"Error getting free/busy info: {e}")
#             return {"error": str(e)}
# import os
# import logging
# from datetime import datetime, timedelta
# from google_auth_oauthlib.flow import InstalledAppFlow
# from google.oauth2.credentials import Credentials
# from google.auth.transport.requests import Request
# from googleapiclient.discovery import build
# from googleapiclient.errors import HttpError

# from langchain.tools import tool  # LangChain tool decorator
# from .BaseTool import BaseTool  # Adjust import as needed

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# class CalendarTool(BaseTool):
#     SCOPES = ['https://www.googleapis.com/auth/calendar']

#     def __init__(self, credentials_file='client_secret.json', token_file='token.json', auth_mode='local'):
#         super().__init__(name="Google Calendar Tool", description="Book and manage Google Calendar events.")
#         self.credentials_file = credentials_file
#         self.token_file = token_file
#         self.auth_mode = auth_mode
#         self.creds = None
#         self.service = None

#     def authenticate(self):
#         if os.path.exists(self.token_file):
#             self.creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)

#         if not self.creds or not self.creds.valid:
#             if self.creds and self.creds.expired and self.creds.refresh_token:
#                 self.creds.refresh(Request())
#             else:
#                 if self.auth_mode == 'local':
#                     flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#                     self.creds = flow.run_local_server(port=0)
#                     with open(self.token_file, 'w') as token:
#                         token.write(self.creds.to_json())
#                 else:
#                     raise Exception("Manual mode selected. Use get_auth_url() and handle_oauth_callback().")

#         self.service = build('calendar', 'v3', credentials=self.creds)

#     def get_auth_url(self):
#         flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#         flow.redirect_uri = 'http://localhost:5000/oauth2callback'
#         auth_url, _ = flow.authorization_url(prompt='consent')
#         return auth_url

#     def handle_oauth_callback(self, authorization_response):
#         flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#         flow.redirect_uri = 'http://localhost:5000/oauth2callback'
#         flow.fetch_token(authorization_response=authorization_response)
#         self.creds = flow.credentials
#         with open(self.token_file, 'w') as token:
#             token.write(self.creds.to_json())

#         self.service = build('calendar', 'v3', credentials=self.creds)
#         return "Authentication successful! You can now use the Calendar API."

#     # @tool("book_appointment")
#     def book_appointment(self, title: str, location: str, description: str, start_time_str: str, duration: float, attendees: list = None) -> dict:
#         try:
#             self.authenticate()

#             try:
#                 start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
#             except ValueError:
#                 return {"error": "Invalid datetime format. Use YYYY-MM-DDTHH:MM:SS"}

#             end_time = start_time + timedelta(hours=duration)

#             event_details = {
#                 'summary': title,
#                 'location': location,
#                 'description': description,
#                 'start': {
#                     'dateTime': start_time.isoformat(),
#                     'timeZone': 'Asia/Kolkata',
#                 },
#                 'end': {
#                     'dateTime': end_time.isoformat(),
#                     'timeZone': 'Asia/Kolkata',
#                 },
#                 'attendees': [{'email': email.strip()} for email in attendees] if attendees else []
#             }

#             event = self.service.events().insert(calendarId='primary', body=event_details).execute()

#             logger.info(f"Event created: {event.get('htmlLink')}")
#             return {
#                 'message': f"Event '{event['summary']}' created successfully.",
#                 'event_link': event.get('htmlLink')
#             }

#         except HttpError as error:
#             logger.error(f"Google Calendar API error: {error}")
#             return {"error": f"Google Calendar API error: {error}"}
#         except Exception as e:
#             logger.exception("Unexpected error")
#             return {"error": str(e)}

#     # @tool("list_events")
#     def list_events(self, max_results: int = 10):
#         try:
#             self.authenticate()
#             now = datetime.utcnow().isoformat() + 'Z'
#             events_result = self.service.events().list(
#                 calendarId='primary', timeMin=now,
#                 maxResults=max_results, singleEvents=True,
#                 orderBy='startTime'
#             ).execute()
#             events = events_result.get('items', [])
#             return events if events else "No upcoming events found."
#         except Exception as e:
#             logger.error(f"Error listing events: {e}")
#             return {"error": str(e)}

#     # @tool("get_event")
#     def get_event(self, event_id: str):
#         try:
#             self.authenticate()
#             event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
#             return event
#         except Exception as e:
#             logger.error(f"Error getting event: {e}")
#             return {"error": str(e)}

#     # @tool("update_event")
#     def update_event(self, event_id: str, updates: dict):
#         """
#         Updates event fields given in the updates dictionary.
#         Example updates: {'summary': 'New Title', 'location': 'New Location'}
#         """
#         try:
#             self.authenticate()
#             event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
#             event.update(updates)
#             updated_event = self.service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
#             return {"message": "Event updated successfully.", "event": updated_event}
#         except Exception as e:
#             logger.error(f"Error updating event: {e}")
#             return {"error": str(e)}

#     # @tool("delete_event")
#     def delete_event(self, event_id: str):
#         try:
#             self.authenticate()
#             self.service.events().delete(calendarId='primary', eventId=event_id).execute()
#             return {"message": f"Event {event_id} deleted successfully."}
#         except Exception as e:
#             logger.error(f"Error deleting event: {e}")
#             return {"error": str(e)}

#     # @tool("list_calendars")
#     def list_calendars(self):
#         try:
#             self.authenticate()
#             calendar_list = self.service.calendarList().list().execute()
#             return calendar_list.get('items', [])
#         except Exception as e:
#             logger.error(f"Error listing calendars: {e}")
#             return {"error": str(e)}

#     # @tool("get_free_busy")
#     def get_free_busy(self, time_min: str, time_max: str, time_zone: str = 'Asia/Kolkata', calendar_ids: list = None):
#         """
#         Check free/busy info for calendars in a time range.
#         time_min, time_max: ISO datetime strings
#         calendar_ids: list of calendar IDs (default is primary calendar)
#         """
#         try:
#             self.authenticate()
#             if calendar_ids is None:
#                 calendar_ids = ['primary']
#             body = {
#                 "timeMin": time_min,
#                 "timeMax": time_max,
#                 "timeZone": time_zone,
#                 "items": [{"id": cal_id} for cal_id in calendar_ids]
#             }
#             freebusy = self.service.freebusy().query(body=body).execute()
#             return freebusy.get('calendars', {})
#         except Exception as e:
#             logger.error(f"Error getting free/busy info: {e}")
#             return {"error": str(e)}
# import os
# import logging
# from datetime import datetime, timedelta
# from google_auth_oauthlib.flow import InstalledAppFlow
# from google.oauth2.credentials import Credentials
# from google.oauth2 import service_account
# from google.auth.transport.requests import Request
# from googleapiclient.discovery import build
# from googleapiclient.errors import HttpError

# from langchain.tools import tool
# from .BaseTool import BaseTool  # Adjust import as needed

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# class CalendarTool(BaseTool):
#     SCOPES = ['https://www.googleapis.com/auth/calendar']

#     def __init__(self,
#                  credentials_file='client_secret.json',
#                  token_file='token.json',
#                  service_account_file='service_account.json',
#                  auth_mode='service_account'):
#         """
#         auth_mode: 'service_account' or 'user_oauth'
#         """
#         super().__init__(name="Google Calendar Tool", description="Book and manage Google Calendar events.")
#         self.credentials_file = credentials_file
#         self.token_file = token_file
#         self.service_account_file = service_account_file
#         self.auth_mode = auth_mode
#         self.creds = None
#         self.service = None
            
#     def get_auth_url(self):
#         """Return Google OAuth2 URL for manual authentication."""
#         flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#         flow.redirect_uri = 'https://jnanic.com/oauth2callback'
#         auth_url, _ = flow.authorization_url(prompt='consent')
#         return auth_url
#     def authenticate(self):
#         """Authenticate with Google Calendar using chosen mode."""
#         if self.auth_mode == 'service_account':
#             if not os.path.exists(self.service_account_file):
#                 raise FileNotFoundError(f"{self.service_account_file} not found")
#             self.creds = service_account.Credentials.from_service_account_file(
#                 self.service_account_file, scopes=self.SCOPES
#             )
#         elif self.auth_mode == 'user_oauth':
#             if os.path.exists(self.token_file):
#                 self.creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)

#             if not self.creds or not self.creds.valid:
#                 if self.creds and self.creds.expired and self.creds.refresh_token:
#                     self.creds.refresh(Request())
#                 else:
#                     flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#                     self.creds = flow.run_local_server(port=0)
#                     with open(self.token_file, 'w') as token:
#                         token.write(self.creds.to_json())
#         else:
#             raise ValueError("auth_mode must be 'service_account' or 'user_oauth'")

#         self.service = build('calendar', 'v3', credentials=self.creds)

#     @tool
#     def book_appointment(self, title: str, location: str, description: str,
#                          start_time_str: str, duration: float, attendees: list = None):
#         """
#         Book a new event in Google Calendar.
#         """
#         try:
#             self.authenticate()
#             start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
#             end_time = start_time + timedelta(hours=duration)

#             event_details = {
#                 'summary': title,
#                 'location': location,
#                 'description': description,
#                 'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
#                 'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
#                 'attendees': [{'email': email.strip()} for email in attendees] if attendees else []
#             }

#             event = self.service.events().insert(calendarId='primary', body=event_details).execute()
#             return {'message': f"Event '{event['summary']}' created successfully.",
#                     'event_link': event.get('htmlLink')}

#         except HttpError as error:
#             logger.error(f"Google Calendar API error: {error}")
#             return {"error": str(error)}
#         except Exception as e:
#             logger.exception("Unexpected error")
#             return {"error": str(e)}

#     @tool
#     def list_events(self, max_results: int = 10):
#         """
#         List upcoming Google Calendar events.
#         """
#         try:
#             self.authenticate()
#             now = datetime.utcnow().isoformat() + 'Z'
#             events_result = self.service.events().list(
#                 calendarId='primary', timeMin=now,
#                 maxResults=max_results, singleEvents=True,
#                 orderBy='startTime'
#             ).execute()
#             events = events_result.get('items', [])
#             return events if events else "No upcoming events found."
#         except Exception as e:
#             logger.error(f"Error listing events: {e}")
#             return {"error": str(e)}

#     @tool
#     def get_event(self, event_id: str):
#         """
#         Get details of a specific Google Calendar event by ID.
#         """
#         try:
#             self.authenticate()
#             event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
#             return event
#         except Exception as e:
#             logger.error(f"Error getting event: {e}")
#             return {"error": str(e)}

#     @tool
#     def update_event(self, event_id: str, updates: dict):
#         """
#         Update an existing Google Calendar event.
#         Example updates: {'summary': 'New Title', 'location': 'New Location'}
#         """
#         try:
#             self.authenticate()
#             event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
#             event.update(updates)
#             updated_event = self.service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
#             return {"message": "Event updated successfully.", "event": updated_event}
#         except Exception as e:
#             logger.error(f"Error updating event: {e}")
#             return {"error": str(e)}

#     @tool
#     def delete_event(self, event_id: str):
#         """
#         Delete a Google Calendar event by ID.
#         """
#         try:
#             self.authenticate()
#             self.service.events().delete(calendarId='primary', eventId=event_id).execute()
#             return {"message": f"Event {event_id} deleted successfully."}
#         except Exception as e:
#             logger.error(f"Error deleting event: {e}")
#             return {"error": str(e)}

#     @tool
#     def list_calendars(self):
#         """
#         List all Google Calendars for the authenticated account.
#         """
#         try:
#             self.authenticate()
#             calendar_list = self.service.calendarList().list().execute()
#             return calendar_list.get('items', [])
#         except Exception as e:
#             logger.error(f"Error listing calendars: {e}")
#             return {"error": str(e)}

#     @tool
#     def get_free_busy(self, time_min: str, time_max: str,
#                       time_zone: str = 'Asia/Kolkata', calendar_ids: list = None):
#         """
#         Check free/busy information for calendars in a given time range.
#         """
#         try:
#             self.authenticate()
#             if calendar_ids is None:
#                 calendar_ids = ['primary']
#             body = {
#                 "timeMin": time_min,
#                 "timeMax": time_max,
#                 "timeZone": time_zone,
#                 "items": [{"id": cal_id} for cal_id in calendar_ids]
#             }
#             freebusy = self.service.freebusy().query(body=body).execute()
#             return freebusy.get('calendars', {})
#         except Exception as e:
#             logger.error(f"Error getting free/busy info: {e}")
#             return {"error": str(e)}

# import os
# import logging
# from datetime import datetime, timedelta
# from google_auth_oauthlib.flow import InstalledAppFlow
# from google.oauth2.credentials import Credentials
# from google.auth.transport.requests import Request
# from googleapiclient.discovery import build
# from googleapiclient.errors import HttpError

# from .BaseTool import BaseTool  # Adjust import as needed

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# class CalendarTool(BaseTool):
#     SCOPES = ['https://www.googleapis.com/auth/calendar']

#     def __init__(self, credentials_file=None, token_file=None, auth_mode='manual'):
#         super().__init__(name="Google Calendar Tool", description="Book and manage Google Calendar events.")
        
#         # Absolute paths
#         base_dir = os.path.dirname(os.path.abspath(__file__))
#         self.credentials_file = credentials_file or os.path.join(base_dir, 'client_secret.json')
#         self.token_file = token_file or os.path.join(base_dir, 'token.json')
        
#         self.auth_mode = auth_mode
#         self.creds = None
#         self.service = None

#     def authenticate(self):
#         """Authenticate with Google Calendar API."""
#         # Load existing token
#         if os.path.exists(self.token_file):
#             self.creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)

#         # Refresh or create credentials
#         if not self.creds or not self.creds.valid:
#             if self.creds and self.creds.expired and self.creds.refresh_token:
#                 self.creds.refresh(Request())
#                 logger.info("Token refreshed successfully.")
#             else:
#                 if self.auth_mode == 'manual':
#                     raise Exception(
#                         "Manual mode selected. Use get_auth_url() and handle_oauth_callback() to authorize first."
#                     )
#                 else:
#                     # Local OAuth (only works if browser available)
#                     flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#                     self.creds = flow.run_local_server(port=0)
#                     with open(self.token_file, 'w') as f:
#                         f.write(self.creds.to_json())
#                     logger.info("Token created successfully using local server flow.")

#         # Initialize Calendar API
#         self.service = build('calendar', 'v3', credentials=self.creds)

#     def get_auth_url(self):
#         """Generate URL for manual OAuth authorization."""
#         flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#         flow.redirect_uri = 'https://jnanic.com/oauth2callback'  # Replace with your actual redirect URI
#         auth_url, _ = flow.authorization_url(prompt='consent')
#         return auth_url
    
#     def handle_oauth_callback(self, authorization_response):
#         """Handle OAuth callback and save token."""
#         flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#         flow.redirect_uri = 'https://jnanic.com/oauth2callback'  # Must match get_auth_url
#         flow.fetch_token(authorization_response=authorization_response)
#         self.creds = flow.credentials

#         # Save token
#         with open(self.token_file, 'w') as f:
#             f.write(self.creds.to_json())
#         logger.info("Authentication successful! Token saved.")

#         # Initialize service
#         self.service = build('calendar', 'v3', credentials=self.creds)
#         return "Authentication successful! You can now use the Calendar API."

#     def book_appointment(self, title: str, location: str, description: str, start_time_str: str,
#                          duration: float, attendees: list = None) -> dict:
#         """Book an appointment in Google Calendar."""
#         try:
#             self.authenticate()
            
#             # Parse start time
#             try:
#                 start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
#             except ValueError:
#                 return {"error": "Invalid datetime format. Use YYYY-MM-DDTHH:MM:SS"}

#             end_time = start_time + timedelta(hours=duration)

#             event_details = {
#                 'summary': title,
#                 'location': location,
#                 'description': description,
#                 'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
#                 'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
#                 'attendees': [{'email': e.strip()} for e in attendees] if attendees else []
#             }

#             event = self.service.events().insert(calendarId='primary', body=event_details).execute()
#             logger.info(f"Event created: {event.get('htmlLink')}")

#             return {"message": f"Event '{event['summary']}' created successfully.",
#                     "event_link": event.get('htmlLink')}

#         except HttpError as e:
#             logger.error(f"Google Calendar API error: {e}")
#             return {"error": str(e)}
#         except Exception as e:
#             logger.exception("Unexpected error")
#             return {"error": str(e)}

#     def list_events(self, max_results: int = 10):
#         """List upcoming events."""
#         try:
#             self.authenticate()
#             now = datetime.utcnow().isoformat() + 'Z'
#             events_result = self.service.events().list(
#                 calendarId='primary', timeMin=now,
#                 maxResults=max_results, singleEvents=True,
#                 orderBy='startTime'
#             ).execute()
#             events = events_result.get('items', [])
#             return events if events else "No upcoming events found."
#         except Exception as e:
#             logger.error(f"Error listing events: {e}")
#             return {"error": str(e)}

#     def get_event(self, event_id: str):
#         """Get a single event by ID."""
#         try:
#             self.authenticate()
#             event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
#             return event
#         except Exception as e:
#             logger.error(f"Error getting event: {e}")
#             return {"error": str(e)}

#     def update_event(self, event_id: str, updates: dict):
#         """Update an existing event."""
#         try:
#             self.authenticate()
#             event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
#             event.update(updates)
#             updated_event = self.service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
#             return {"message": "Event updated successfully.", "event": updated_event}
#         except Exception as e:
#             logger.error(f"Error updating event: {e}")
#             return {"error": str(e)}

#     def delete_event(self, event_id: str):
#         """Delete an event."""
#         try:
#             self.authenticate()
#             self.service.events().delete(calendarId='primary', eventId=event_id).execute()
#             return {"message": f"Event {event_id} deleted successfully."}
#         except Exception as e:
#             logger.error(f"Error deleting event: {e}")
#             return {"error": str(e)}

#     def list_calendars(self):
#         """List all calendars."""
#         try:
#             self.authenticate()
#             calendars = self.service.calendarList().list().execute()
#             return calendars.get('items', [])
#         except Exception as e:
#             logger.error(f"Error listing calendars: {e}")
#             return {"error": str(e)}

#     def get_free_busy(self, time_min: str, time_max: str, time_zone='Asia/Kolkata', calendar_ids=None):
#         """Check free/busy info for given calendars."""
#         try:
#             self.authenticate()
#             if calendar_ids is None:
#                 calendar_ids = ['primary']
#             body = {
#                 "timeMin": time_min,
#                 "timeMax": time_max,
#                 "timeZone": time_zone,
#                 "items": [{"id": cal_id} for cal_id in calendar_ids]
#             }
#             freebusy = self.service.freebusy().query(body=body).execute()
#             return freebusy.get('calendars', {})
#         except Exception as e:
#             logger.error(f"Error getting free/busy info: {e}")
#             return {"error": str(e)}
# import os
# import logging
# from datetime import datetime, timedelta
# from google.auth.transport.requests import Request
# from google.oauth2 import service_account
# from google_auth_oauthlib.flow import InstalledAppFlow
# from google.oauth2.credentials import Credentials
# from googleapiclient.discovery import build
# from googleapiclient.errors import HttpError

# from .BaseTool import BaseTool  # Adjust import as needed

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# class CalendarTool(BaseTool):
#     SCOPES = ['https://www.googleapis.com/auth/calendar']

#     def __init__(self, 
#                  credentials_file='client_secret.json', 
#                  token_file='token.json', 
#                  service_account_file='service_account.json',
#                  auth_mode='local',
#                  redirect_uri='https://jnanic.com/oauth2callback'):
#         """
#         auth_mode: 
#           - 'local'   (OAuth2, local server)
#           - 'manual'  (OAuth2, manual redirect for server deployment)
#           - 'service' (service_account)
#         """
#         super().__init__(name="Google Calendar Tool", description="Book and manage Google Calendar events.")
#         self.credentials_file = credentials_file
#         self.token_file = token_file
#         self.service_account_file = service_account_file
#         self.auth_mode = auth_mode
#         self.redirect_uri = redirect_uri
#         self.creds = None
#         self.service = None

#     def authenticate(self):
#         """
#         Authenticate user/service account depending on auth_mode
#         """
#         if self.auth_mode == 'service':
#             logger.info("Authenticating with Service Account...")
#             self.creds = service_account.Credentials.from_service_account_file(
#                 self.service_account_file, scopes=self.SCOPES
#             )
#             # Optional: impersonate a user (if needed for primary user calendar)
#             # self.creds = self.creds.with_subject("your_user@domain.com")

#         elif self.auth_mode == 'local':
#             logger.info("Authenticating with local OAuth flow...")
#             if os.path.exists(self.token_file):
#                 self.creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)

#             if not self.creds or not self.creds.valid:
#                 if self.creds and self.creds.expired and self.creds.refresh_token:
#                     self.creds.refresh(Request())
#                 else:
#                     flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#                     self.creds = flow.run_local_server(port=0)
#                     with open(self.token_file, 'w') as token:
#                         token.write(self.creds.to_json())

#         elif self.auth_mode == 'manual':
#             # In manual mode, we expect token.json to exist after callback
#             logger.info("Manual auth mode selected. Using saved credentials if available.")
#             if os.path.exists(self.token_file):
#                 self.creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)
#             else:
#                 raise Exception("Manual mode: No credentials found. Use get_auth_url() and handle_oauth_callback().")

#             if not self.creds or not self.creds.valid:
#                 if self.creds and self.creds.expired and self.creds.refresh_token:
#                     self.creds.refresh(Request())
#                 else:
#                     raise Exception("Manual mode: Credentials invalid. Re-authenticate with Google OAuth.")

#         else:
#             raise Exception(f"Invalid auth_mode: {self.auth_mode}")

#         self.service = build('calendar', 'v3', credentials=self.creds)

#     def get_auth_url(self):
#         """Generate the Google OAuth consent screen URL."""
#         flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#         flow.redirect_uri = self.redirect_uri
#         auth_url, _ = flow.authorization_url(prompt='consent')
#         return auth_url

#     def handle_oauth_callback(self, authorization_response):
#         """Exchange auth code for tokens and save them."""
#         flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
#         flow.redirect_uri = self.redirect_uri
#         flow.fetch_token(authorization_response=authorization_response)
#         self.creds = flow.credentials

#         with open(self.token_file, 'w') as token:
#             token.write(self.creds.to_json())

#         self.service = build('calendar', 'v3', credentials=self.creds)
#         return "✅ Authentication successful! You can now use the Calendar API."

#     # ---------------- Calendar Operations ---------------- #

#     def book_appointment(self, title: str, location: str, description: str, start_time_str: str, duration: float, attendees: list = None) -> dict:
#         try:
#             self.authenticate()

#             try:
#                 start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
#             except ValueError:
#                 return {"error": "Invalid datetime format. Use YYYY-MM-DDTHH:MM:SS"}

#             end_time = start_time + timedelta(hours=duration)

#             event_details = {
#                 'summary': title,
#                 'location': location,
#                 'description': description,
#                 'start': {
#                     'dateTime': start_time.isoformat(),
#                     'timeZone': 'Asia/Kolkata',
#                 },
#                 'end': {
#                     'dateTime': end_time.isoformat(),
#                     'timeZone': 'Asia/Kolkata',
#                 },
#                 'attendees': [{'email': email.strip()} for email in attendees] if attendees else []
#             }

#             event = self.service.events().insert(calendarId='primary', body=event_details).execute()
#             logger.info(f"Event created: {event.get('htmlLink')}")
#             return {
#                 'message': f"Event '{event['summary']}' created successfully.",
#                 'event_link': event.get('htmlLink')
#             }

#         except HttpError as error:
#             logger.error(f"Google Calendar API error: {error}")
#             return {"error": f"Google Calendar API error: {error}"}
#         except Exception as e:
#             logger.exception("Unexpected error")
#             return {"error": str(e)}

#     def list_events(self, max_results: int = 10):
#         try:
#             self.authenticate()
#             now = datetime.utcnow().isoformat() + 'Z'
#             events_result = self.service.events().list(
#                 calendarId='primary', timeMin=now,
#                 maxResults=max_results, singleEvents=True,
#                 orderBy='startTime'
#             ).execute()
#             events = events_result.get('items', [])
#             return events if events else "No upcoming events found."
#         except Exception as e:
#             logger.error(f"Error listing events: {e}")
#             return {"error": str(e)}

#     def get_event(self, event_id: str):
#         try:
#             self.authenticate()
#             event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
#             return event
#         except Exception as e:
#             logger.error(f"Error getting event: {e}")
#             return {"error": str(e)}

#     def update_event(self, event_id: str, updates: dict):
#         try:
#             self.authenticate()
#             event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
#             event.update(updates)
#             updated_event = self.service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
#             return {"message": "Event updated successfully.", "event": updated_event}
#         except Exception as e:
#             logger.error(f"Error updating event: {e}")
#             return {"error": str(e)}

#     def delete_event(self, event_id: str):
#         try:
#             self.authenticate()
#             self.service.events().delete(calendarId='primary', eventId=event_id).execute()
#             return {"message": f"Event {event_id} deleted successfully."}
#         except Exception as e:
#             logger.error(f"Error deleting event: {e}")
#             return {"error": str(e)}

#     def list_calendars(self):
#         try:
#             self.authenticate()
#             calendar_list = self.service.calendarList().list().execute()
#             return calendar_list.get('items', [])
#         except Exception as e:
#             logger.error(f"Error listing calendars: {e}")
#             return {"error": str(e)}

#     def get_free_busy(self, time_min: str, time_max: str, time_zone: str = 'Asia/Kolkata', calendar_ids: list = None):
#         try:
#             self.authenticate()
#             if calendar_ids is None:
#                 calendar_ids = ['primary']
#             body = {
#                 "timeMin": time_min,
#                 "timeMax": time_max,
#                 "timeZone": time_zone,
#                 "items": [{"id": cal_id} for cal_id in calendar_ids]
#             }
#             freebusy = self.service.freebusy().query(body=body).execute()
#             return freebusy.get('calendars', {})
#         except Exception as e:
#             logger.error(f"Error getting free/busy info: {e}")
#             return {"error": str(e)}
import os
import logging
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import Flow
from .BaseTool import BaseTool  # Adjust if needed


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CalendarTool(BaseTool):
    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    # def __init__(self,
    #              credentials_file="client_secret.json",
    #              token_file="token.json",
    #              redirect_uri="https://api.jnanic.com/oauth2callback",
    #              auth_mode="manual"):
    #     super().__init__(name="Google Calendar Tool", description="Book and manage Google Calendar events.")
    #     self.credentials_file = credentials_file
    #     self.token_file = token_file
    #     self.redirect_uri = redirect_uri
    #     self.auth_mode = auth_mode
    #     self.creds = None
    #     self.service = None  # <-- don't build yet
    #     self.flow = None

    # ---------------- Authentication ---------------- #
    def __init__(self,
                 credentials_file="client_secret.json",
                 token_file="token.json",
                 redirect_uri="https://api.jnanic.com/multi_agents/oauth2callback",
                 auth_mode="manual"):
        super().__init__(name="Google Calendar Tool", description="Book and manage Google Calendar events.")
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.redirect_uri = redirect_uri
        self.auth_mode = auth_mode
        self.creds = None
        self.service = None  # <-- don't build yet
        self.flow = None

    def get_auth_url(self):
        """Generate Google OAuth consent screen URL."""
        self.flow = Flow.from_client_secrets_file(
            self.credentials_file,
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri,
        )
        auth_url, state = self.flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
        )
        return auth_url, state

    def handle_oauth_callback(self, authorization_response, state):
        """Exchange auth code for tokens and save them."""
        if not self.flow:
            self.flow = Flow.from_client_secrets_file(
                self.credentials_file,
                scopes=self.SCOPES,
                redirect_uri=self.redirect_uri,
            )
        self.flow.fetch_token(authorization_response=authorization_response)

        self.creds = self.flow.credentials
        with open(self.token_file, "w") as token:
            token.write(self.creds.to_json())

        self.service = build("calendar", "v3", credentials=self.creds)
        return "✅ Authentication successful!"


    # ---------------- Calendar Operations ---------------- #

    def book_appointment(self, title: str, location: str, description: str,
                         start_time_str: str, duration: float, attendees: list = None) -> dict:
        try:
            self.authenticate()

            try:
                start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                return {"error": "Invalid datetime format. Use YYYY-MM-DDTHH:MM:SS"}

            end_time = start_time + timedelta(hours=duration)

            event_details = {
                "summary": title,
                "location": location,
                "description": description,
                "start": {"dateTime": start_time.isoformat(), "timeZone": "Asia/Kolkata"},
                "end": {"dateTime": end_time.isoformat(), "timeZone": "Asia/Kolkata"},
                "attendees": [{"email": email.strip()} for email in attendees] if attendees else []
            }

            event = self.service.events().insert(calendarId="primary", body=event_details).execute()
            logger.info(f"Event created: {event.get('htmlLink')}")
            return {"message": f"Event '{event['summary']}' created successfully.",
                    "event_link": event.get("htmlLink")}

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return {"error": f"Google Calendar API error: {error}"}
        except Exception as e:
            logger.exception("Unexpected error")
            return {"error": str(e)}

    def list_events(self, max_results: int = 10):
        try:
            self.authenticate()
            now = datetime.utcnow().isoformat() + "Z"
            events_result = self.service.events().list(
                calendarId="primary", timeMin=now,
                maxResults=max_results, singleEvents=True,
                orderBy="startTime"
            ).execute()
            events = events_result.get("items", [])
            return events if events else "No upcoming events found."
        except Exception as e:
            logger.error(f"Error listing events: {e}")
            return {"error": str(e)}

    def get_event(self, event_id: str):
        try:
            self.authenticate()
            return self.service.events().get(calendarId="primary", eventId=event_id).execute()
        except Exception as e:
            logger.error(f"Error getting event: {e}")
            return {"error": str(e)}

    def update_event(self, event_id: str, updates: dict):
        try:
            self.authenticate()
            event = self.service.events().get(calendarId="primary", eventId=event_id).execute()
            event.update(updates)
            updated_event = self.service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
            return {"message": "Event updated successfully.", "event": updated_event}
        except Exception as e:
            logger.error(f"Error updating event: {e}")
            return {"error": str(e)}

    def delete_event(self, event_id: str):
        try:
            self.authenticate()
            self.service.events().delete(calendarId="primary", eventId=event_id).execute()
            return {"message": f"Event {event_id} deleted successfully."}
        except Exception as e:
            logger.error(f"Error deleting event: {e}")
            return {"error": str(e)}

    def list_calendars(self):
        try:
            self.authenticate()
            calendar_list = self.service.calendarList().list().execute()
            return calendar_list.get("items", [])
        except Exception as e:
            logger.error(f"Error listing calendars: {e}")
            return {"error": str(e)}

    def get_free_busy(self, time_min: str, time_max: str,
                      time_zone: str = "Asia/Kolkata", calendar_ids: list = None):
        try:
            self.authenticate()
            if calendar_ids is None:
                calendar_ids = ["primary"]
            body = {
                "timeMin": time_min,
                "timeMax": time_max,
                "timeZone": time_zone,
                "items": [{"id": cal_id} for cal_id in calendar_ids]
            }
            freebusy = self.service.freebusy().query(body=body).execute()
            return freebusy.get("calendars", {})
        except Exception as e:
            logger.error(f"Error getting free/busy info: {e}")
            return {"error": str(e)}
