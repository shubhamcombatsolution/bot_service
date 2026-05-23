import os
from flask import Flask, redirect, request, jsonify
from google_auth_oauthlib.flow import InstalledAppFlow 
from google.oauth2.credentials import Credentials

from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
from datetime import datetime, timedelta
# Google Calendar API configuration
SCOPES = ['https://www.googleapis.com/auth/calendar']
CLIENT_SECRET_FILE = 'client_secret.json'  # Path to your downloaded client_secret.json file

app = Flask(__name__)


def get_google_calendar_service():
    """Authenticate and return the Google Calendar API service object."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("Credentials are not available or invalid.")

    return build('calendar', 'v3', credentials=creds)

@app.route('/')
def index():
    """Redirect to the Google authorization URL.""" 
    creds = None

    # The file token.json stores the user's access and refresh tokens
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES)
            
            # Use localhost for redirect_uri during testing
            flow.redirect_uri = 'http://127.0.0.1:5000/multi_agents/oauth2callback'

            auth_url, _ = flow.authorization_url(prompt='consent')
            return redirect(auth_url)  # Redirect the user to the authorization URL
    
    return 'You are already authenticated.'

@app.route('/oauth2callback')
def oauth2callback():
    """Handle the OAuth2 callback."""
    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRET_FILE, SCOPES)
    flow.redirect_uri = 'http://127.0.0.1:5000/multi_agents/oauth2callback'

    # Get the authorization code from the query parameters
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials

    # Save the credentials for later use
    with open('token.json', 'w') as token:
        token.write(creds.to_json())

    return 'Authentication successful! You can now access your Google Calendar.'
 
 
@app.route('/book-appointment', methods=['POST'])
def book_appointment():
    """Endpoint to book an appointment in Google Calendar."""
    try:
        data = request.json
        title = data.get('title', 'Appointment')
        location = data.get('location', '')
        description = data.get('description', '')
        start_time_str = data.get('start_time')
        duration = int(data.get('duration', 1))  # Default duration 1 hour

        # Parse start_time to datetime
        start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
        end_time = start_time + timedelta(hours=duration)

        # Create event details
        event_details = {
            'summary': title,
            'location': location,
            'description': description,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'Asia/Kolkata',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'Asia/Kolkata',
            },
        }

        # Schedule event in Google Calendar
        service = get_google_calendar_service()
        event = service.events().insert(calendarId='primary', body=event_details).execute()
        print(f"event {event}")
        return jsonify({
            'message': f"Event '{event['summary']}' created successfully.",
            'event_link': event.get('htmlLink')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 400

