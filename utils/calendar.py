import os
import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from dotenv import load_dotenv

load_dotenv()
SCOPES = ['https://www.googleapis.com/auth/calendar.events', 'https://www.googleapis.com/auth/calendar.readonly']
CALENDAR_ID = os.getenv('GOOGLE_CALENDAR_ID', 'primary')

def get_calendar_service():
    creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    return build('calendar', 'v3', credentials=creds)

def add_event(summary, description, start_time, end_time, timezone='Asia/Kolkata'):
    """
    Adds an event to Google Calendar.
    """
    service = get_calendar_service()
    event = {
        'summary': summary,
        'description': description,
        'start': {'dateTime': start_time, 'timeZone': timezone},
        'end': {'dateTime': end_time, 'timeZone': timezone},
    }
    created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return created_event.get('htmlLink')

def list_upcoming_events(days: int = 7):
    """
    Lists upcoming events in the next X days.
    """
    service = get_calendar_service()
    
    now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
    end_time = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat() + 'Z'
    
    events_result = service.events().list(
        calendarId=CALENDAR_ID, 
        timeMin=now,
        timeMax=end_time,
        maxResults=20, 
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    if not events:
        return "No upcoming events found."
        
    res = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        link = event.get('htmlLink', '')
        res.append(f"- {event['summary']} at {start} (Link: {link})")
        
    return "\n".join(res)
