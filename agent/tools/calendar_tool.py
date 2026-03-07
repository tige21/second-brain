import json
from langchain_core.tools import tool
from services import google_calendar as gcal


@tool
def get_calendar_events(start_datetime: str, end_datetime: str) -> str:
    """
    Get Google Calendar events for a date range.
    start_datetime and end_datetime must be ISO 8601 UTC strings, e.g. "2024-01-15T00:00:00Z".
    Returns JSON array of events with id, summary, start, end, location, recurringEventId fields.
    """
    try:
        events = gcal.list_events(start_datetime, end_datetime)
        result = []
        for e in events:
            result.append({
                "id": e.get("id"),
                "summary": e.get("summary", ""),
                "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
                "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
                "location": e.get("location"),
                "recurringEventId": e.get("recurringEventId"),
            })
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return f"Ошибка при получении событий: {e}"


@tool
def create_calendar_event(
    summary: str,
    start_utc: str,
    end_utc: str,
    location: str = None,
    description: str = None,
    recurrence: str = None,
) -> str:
    """
    Create a Google Calendar event.
    summary: event title (use user's exact words).
    start_utc / end_utc: ISO 8601 UTC, e.g. "2024-01-15T11:00:00Z".
    location: optional venue address.
    description: optional notes.
    recurrence: optional RRULE string WITHOUT "RRULE:" prefix, e.g. "FREQ=WEEKLY;BYDAY=SA,SU".
    """
    try:
        rec = [recurrence] if recurrence else None
        event = gcal.create_event(summary, start_utc, end_utc, location, description, rec)
        return f"✅ Событие создано: {event['summary']} (id: {event['id']})"
    except Exception as e:
        return f"Ошибка при создании события: {e}"


@tool
def update_calendar_event(
    event_id: str,
    summary: str = None,
    start_utc: str = None,
    end_utc: str = None,
    location: str = None,
    description: str = None,
) -> str:
    """
    Update an existing Google Calendar event by event_id.
    Only provide fields that need to be changed. Others will be left unchanged.
    For a single occurrence of recurring event: use instance ID (contains underscore).
    For entire series: use recurringEventId.
    To delete this and all future occurrences: use delete_future_occurrences tool instead.
    """
    try:
        fields = {}
        if summary:
            fields['summary'] = summary
        if start_utc:
            fields['start'] = start_utc
        if end_utc:
            fields['end'] = end_utc
        if location is not None:
            fields['location'] = location
        if description is not None:
            fields['description'] = description
        event = gcal.update_event(event_id, **fields)
        return f"✅ Событие обновлено: {event.get('summary')} (id: {event_id})"
    except Exception as e:
        return f"Ошибка при обновлении события: {e}"


@tool
def delete_future_occurrences(instance_id: str) -> str:
    """
    Delete this and ALL FOLLOWING occurrences of a recurring event.
    Use when user says: "убрать с этой недели", "удалить со следующего раза",
    "убрать все последующие", "отменить начиная с сегодня".
    instance_id: the ID of the specific recurring event instance (contains underscore _).
    The parent recurring event will be updated to end before this instance.
    """
    try:
        result = gcal.delete_this_and_following(instance_id)
        if result.get("status") == "deleted single event":
            return "✅ Одиночное событие удалено."
        return f"✅ Это и все последующие повторения удалены. Серия завершена до этой даты."
    except Exception as e:
        return f"Ошибка при удалении последующих событий: {e}"
