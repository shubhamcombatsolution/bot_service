from flask import Flask, redirect, request, session, url_for
import os
import pathlib
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "replace-me-with-a-secure-secret")

# Path to your client_secret.json
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Home page
@app.route("/")
def index():
    return '<a href="/authorize">Login with Google</a>'

# Step 1: Redirect user to Google OAuth
@app.route("/authorize")
def authorize():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for("oauth2callback", _external=True)
    )
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true"
    )
    session["state"] = state
    return redirect(authorization_url)

# Step 2: Handle OAuth2 callback
@app.route("/oauth2callback")
def oauth2callback():
    state = session["state"]
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=url_for("oauth2callback", _external=True)
    )
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials
    # Save credentials in session (or DB)
    session["credentials"] = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes
    }

    return redirect(url_for("calendar_events"))

# Step 3: Access Google Calendar
@app.route("/calendar")
def calendar_events():
    if "credentials" not in session:
        return redirect(url_for("authorize"))

    creds = Credentials(**session["credentials"])
    service = build("calendar", "v3", credentials=creds)

    # Get next 10 events
    events_result = service.events().list(calendarId="primary", maxResults=10).execute()
    events = events_result.get("items", [])

    events_list = "<h1>Upcoming Events:</h1>"
    if not events:
        events_list += "<p>No upcoming events found.</p>"
    else:
        for event in events:
            events_list += f"<p>{event['summary']} - {event.get('start', {}).get('dateTime', event.get('start', {}).get('date'))}</p>"

    return events_list

if __name__ == "__main__":
    app.run(debug=True)
