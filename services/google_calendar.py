from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
from tenacity import retry, stop_after_attempt, wait_exponential
from services.google_auth import get_credentials
from config import GOOGLE_CALENDAR_ID


def _service():
    return build('calendar', 'v3', credentials=get_credentials())


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def list_events(time_min: str, time_max: str, single_events: bool = True) -> list[dict]:
    result = _service().events().list(
        calendarId=GOOGLE_CALENDAR_ID,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=single_events,
        orderBy='startTime',
        maxResults=100,
    ).execute()
    return result.get('items', [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def create_event(
    summary: str,
    start_utc: str,
    end_utc: str,
    location: str = None,
    description: str = None,
    recurrence: list[str] = None,
) -> dict:
    body = {
        'summary': summary,
        'start': {'dateTime': start_utc, 'timeZone': 'UTC'},
        'end': {'dateTime': end_utc, 'timeZone': 'UTC'},
    }
    if location:
        body['location'] = location
    if description:
        body['description'] = description
    if recurrence:
        body['recurrence'] = [
            f"RRULE:{r}" if not r.startswith("RRULE:") else r
            for r in recurrence
        ]
    return _service().events().insert(calendarId=GOOGLE_CALENDAR_ID, body=body).execute()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def update_event(event_id: str, **fields) -> dict:
    event = _service().events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()
    for key, value in fields.items():
        if key in ('start', 'end') and isinstance(value, str):
            event[key] = {'dateTime': value, 'timeZone': 'UTC'}
        else:
            event[key] = value
    return _service().events().update(
        calendarId=GOOGLE_CALENDAR_ID, eventId=event_id, body=event
    ).execute()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def delete_event(event_id: str) -> None:
    _service().events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()


def get_today_range() -> tuple[str, str]:
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = now + timedelta(days=1)
    return now.isoformat(), tomorrow.isoformat()


def get_today_and_tomorrow_range() -> tuple[str, str]:
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day_after = now + timedelta(days=2)
    return now.isoformat(), day_after.isoformat()
