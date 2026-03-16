import re
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_not_exception_type
from services.google_auth import get_credentials, GoogleAuthExpiredError

_retry = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_not_exception_type(GoogleAuthExpiredError),
)
from config import GOOGLE_CALENDAR_ID


def _service(chat_id: int):
    return build('calendar', 'v3', credentials=get_credentials(chat_id))


@retry(**_retry)
def list_events(chat_id: int, time_min: str, time_max: str, single_events: bool = True) -> list[dict]:
    result = _service(chat_id).events().list(
        calendarId=GOOGLE_CALENDAR_ID,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=single_events,
        orderBy='startTime',
        maxResults=100,
    ).execute()
    return result.get('items', [])


@retry(**_retry)
def create_event(
    chat_id: int,
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
    return _service(chat_id).events().insert(calendarId=GOOGLE_CALENDAR_ID, body=body).execute()


@retry(**_retry)
def update_event(chat_id: int, event_id: str, **fields) -> dict:
    svc = _service(chat_id)
    event = svc.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()

    # Recurrence can only be updated on the parent event, not on instances.
    # If this is an instance (has recurringEventId) and we're changing recurrence,
    # automatically redirect to the parent event.
    if 'recurrence' in fields and event.get('recurringEventId'):
        parent_id = event['recurringEventId']
        event = svc.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=parent_id).execute()
        event_id = parent_id

    # If start is being moved but end is not specified, auto-adjust end to preserve duration.
    if 'start' in fields and 'end' not in fields:
        orig_start_str = event.get('start', {}).get('dateTime')
        orig_end_str = event.get('end', {}).get('dateTime')
        if orig_start_str and orig_end_str:
            orig_start = datetime.fromisoformat(orig_start_str.replace('Z', '+00:00'))
            orig_end = datetime.fromisoformat(orig_end_str.replace('Z', '+00:00'))
            duration = orig_end - orig_start
            new_start_str = fields['start'] if isinstance(fields['start'], str) else fields['start'].get('dateTime', orig_start_str)
            new_start = datetime.fromisoformat(new_start_str.replace('Z', '+00:00'))
            fields['end'] = (new_start + duration).strftime('%Y-%m-%dT%H:%M:%SZ')

    for key, value in fields.items():
        if key in ('start', 'end') and isinstance(value, str):
            event[key] = {'dateTime': value, 'timeZone': 'UTC'}
        elif key == 'recurrence':
            if isinstance(value, str):
                value = [value]
            event[key] = [
                f"RRULE:{r}" if not r.startswith("RRULE:") else r
                for r in value
            ]
        else:
            event[key] = value

    return svc.events().update(
        calendarId=GOOGLE_CALENDAR_ID, eventId=event_id, body=event
    ).execute()


@retry(**_retry)
def delete_event(chat_id: int, event_id: str) -> None:
    _service(chat_id).events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()


def delete_event_or_series(chat_id: int, event_id: str) -> str:
    """
    Delete a single event or an entire recurring series.
    If event_id is a recurring instance (contains '_'), resolves to the parent
    recurringEventId and deletes the whole series.
    Returns the ID that was actually deleted.
    """
    svc = _service(chat_id)
    target_id = event_id
    if '_' in event_id:
        event = svc.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()
        parent_id = event.get('recurringEventId')
        if parent_id:
            target_id = parent_id
    svc.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=target_id).execute()
    return target_id


def delete_this_and_following(chat_id: int, instance_id: str) -> dict:
    """
    Delete this and all following occurrences of a recurring event.
    Works by updating the parent event's RRULE to set UNTIL = day before this instance.
    """
    svc = _service(chat_id)

    instance = svc.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=instance_id).execute()
    recurring_event_id = instance.get('recurringEventId')
    if not recurring_event_id:
        svc.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=instance_id).execute()
        return {"status": "deleted single event"}

    start = instance.get('start', {})
    start_str = start.get('dateTime') or start.get('date', '')
    is_all_day = 'T' not in start_str
    if is_all_day:
        # All-day event: UNTIL must be a DATE (RFC 5545 §3.3.10)
        instance_date = datetime.strptime(start_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        until_str = (instance_date - timedelta(days=1)).strftime('%Y%m%d')
    else:
        instance_date = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        until_str = (instance_date - timedelta(seconds=1)).strftime('%Y%m%dT%H%M%SZ')

    parent = svc.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=recurring_event_id).execute()
    recurrence = parent.get('recurrence', [])

    updated_recurrence = []
    for rule in recurrence:
        if rule.startswith('RRULE:'):
            rule_body = rule[6:]
            rule_body = re.sub(r';?UNTIL=[^;]+', '', rule_body)
            rule_body = re.sub(r';?COUNT=\d+', '', rule_body)
            rule_body = rule_body.strip(';')
            rule = f"RRULE:{rule_body};UNTIL={until_str}"
        updated_recurrence.append(rule)

    parent['recurrence'] = updated_recurrence
    return svc.events().update(
        calendarId=GOOGLE_CALENDAR_ID, eventId=recurring_event_id, body=parent
    ).execute()


def delete_single_occurrence(chat_id: int, instance_id: str) -> dict:
    """
    Delete only one occurrence of a recurring event.
    Calling delete() on an instance_id creates a 'cancelled' exception
    for that date only — all other occurrences remain untouched.
    Returns the event dict (for summary/undo) before deleting.
    """
    svc = _service(chat_id)
    event = svc.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=instance_id).execute()
    svc.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=instance_id).execute()
    return event


def restore_occurrence(chat_id: int, instance_id: str) -> None:
    """
    Restore a previously cancelled recurring event instance.
    Patches the instance status back to 'confirmed'.
    """
    _service(chat_id).events().patch(
        calendarId=GOOGLE_CALENDAR_ID,
        eventId=instance_id,
        body={'status': 'confirmed'},
    ).execute()


def exclude_weekday_from_recurrence(chat_id: int, event_id: str, weekday: str) -> dict:
    """
    Permanently remove a weekday from a recurring event's RRULE.
    weekday: two-letter code MO|TU|WE|TH|FR|SA|SU.
    Works with any event_id — resolves to parent automatically.
    Handles FREQ=DAILY by converting to FREQ=WEEKLY with all days except the excluded one.
    """
    all_days = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
    svc = _service(chat_id)

    # Resolve to parent event
    event = svc.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()
    parent_id = event.get('recurringEventId') or event_id
    if parent_id != event_id:
        event = svc.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=parent_id).execute()

    recurrence = event.get('recurrence', [])
    new_recurrence = []
    for rule in recurrence:
        if not rule.startswith('RRULE:'):
            new_recurrence.append(rule)
            continue

        parts = dict(p.split('=', 1) for p in rule[6:].split(';') if '=' in p)
        freq = parts.get('FREQ', '')
        byday = parts.get('BYDAY', '')

        if freq == 'DAILY':
            # Convert DAILY → WEEKLY with all days except the excluded one
            days = [d for d in all_days if d != weekday]
            parts['FREQ'] = 'WEEKLY'
            parts['BYDAY'] = ','.join(days)
        elif freq == 'WEEKLY' and byday:
            current_days = [d.strip() for d in byday.split(',')]
            days = [d for d in current_days if d != weekday]
            if not days:
                raise ValueError(f"Cannot remove {weekday}: it is the only day in the schedule")
            parts['BYDAY'] = ','.join(days)

        new_recurrence.append('RRULE:' + ';'.join(f'{k}={v}' for k, v in parts.items()))

    event['recurrence'] = new_recurrence
    return svc.events().update(calendarId=GOOGLE_CALENDAR_ID, eventId=parent_id, body=event).execute()


def get_today_range() -> tuple[str, str]:
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = now + timedelta(days=1)
    return now.isoformat(), tomorrow.isoformat()


def get_today_and_tomorrow_range() -> tuple[str, str]:
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day_after = now + timedelta(days=2)
    return now.isoformat(), day_after.isoformat()
