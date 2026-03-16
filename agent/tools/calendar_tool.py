import json
from datetime import datetime, timedelta
from langchain_core.tools import tool
from services import google_calendar as gcal
from services.google_auth import GoogleAuthExpiredError
from db.database import get_conn
from db.models import push_undo, get_setting
from agent.context import get_current_chat_id, get_current_session_id
from config import TIMEZONE_OFFSET

_AUTH_ERROR_MSG = "❌ Авторизация Google истекла. Отправь /connect для повторной авторизации."


def _to_utc(dt_str: str | None, tz_offset: int) -> str | None:
    """Convert local datetime string to UTC ISO format.

    - No suffix (e.g. "2026-03-18T09:50:00")  → subtract tz_offset → UTC with Z
    - Already has Z or explicit offset (+/-HH:MM) → return as-is
    """
    if not dt_str:
        return dt_str
    # Already explicit UTC or has timezone offset
    if dt_str.endswith('Z') or (len(dt_str) > 10 and dt_str[-6] in ('+', '-')):
        return dt_str
    # Local time without suffix — convert to UTC
    local_dt = datetime.fromisoformat(dt_str)
    utc_dt = local_dt - timedelta(hours=tz_offset)
    return utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ')


@tool
def get_calendar_events(start_datetime: str, end_datetime: str) -> str:
    """
    Get Google Calendar events for a date range.
    start_datetime and end_datetime must be ISO 8601 UTC strings, e.g. "2024-01-15T00:00:00Z".
    Returns JSON array of events with id, summary, start, end, location, recurringEventId fields.
    """
    try:
        chat_id = get_current_chat_id()
        events = gcal.list_events(chat_id, start_datetime, end_datetime)
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
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при получении событий: {e}"


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
    start_utc / end_utc: pass LOCAL time WITHOUT timezone suffix, e.g. "2026-03-18T14:00:00".
      Conversion to UTC is done automatically. Do NOT subtract the timezone offset yourself.
    location: optional venue address.
    description: optional notes.
    recurrence: optional RRULE string WITHOUT "RRULE:" prefix, e.g. "FREQ=WEEKLY;BYDAY=SA,SU".
    """
    try:
        chat_id = get_current_chat_id()
        tz_offset = int(get_setting(get_conn(), chat_id, 'timezone_offset') or TIMEZONE_OFFSET)
        start = _to_utc(start_utc, tz_offset)
        end = _to_utc(end_utc, tz_offset)
        rec = [recurrence] if recurrence else None
        event = gcal.create_event(chat_id, summary, start, end, location, description, rec)
        push_undo(get_conn(), chat_id, 'create_event', event['id'], event['summary'], get_current_session_id())
        return f"✅ Событие создано: {event['summary']} (id: {event['id']})"
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при создании события: {e}"


@tool
def update_calendar_event(
    event_id: str,
    summary: str = None,
    start_utc: str = None,
    end_utc: str = None,
    location: str = None,
    description: str = None,
    recurrence: str = None,
) -> str:
    """
    Update an existing Google Calendar event by event_id.
    Only provide fields that need to be changed. Others will be left unchanged.
    start_utc / end_utc: pass LOCAL time WITHOUT timezone suffix, e.g. "2026-03-18T14:00:00".
      Conversion to UTC is done automatically. Do NOT subtract the timezone offset yourself.
    For a single occurrence of recurring event: use instance ID (contains underscore).
    For entire series: use recurringEventId.
    To delete this and all future occurrences: use delete_future_occurrences tool instead.
    recurrence: new RRULE without "RRULE:" prefix, e.g. "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR".
    When changing recurrence of a series, any event_id (instance or parent) works — the
    parent event is updated automatically. Use for: "убрать с выходных", "только по будням", etc.
    """
    try:
        chat_id = get_current_chat_id()
        tz_offset = int(get_setting(get_conn(), chat_id, 'timezone_offset') or TIMEZONE_OFFSET)
        fields = {}
        if summary:
            fields['summary'] = summary
        if start_utc:
            fields['start'] = _to_utc(start_utc, tz_offset)
        if end_utc:
            fields['end'] = _to_utc(end_utc, tz_offset)
        if location is not None:
            fields['location'] = location
        if description is not None:
            fields['description'] = description
        if recurrence is not None:
            fields['recurrence'] = recurrence
        if not fields:
            return "❌ Не указано ни одного поля для обновления. Укажи что именно нужно изменить."
        event = gcal.update_event(chat_id, event_id, **fields)
        return f"✅ Событие обновлено: {event.get('summary')} (id: {event_id})"
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при обновлении события: {e}"


@tool
def delete_calendar_event(event_id: str) -> str:
    """
    Fully delete a calendar event or an ENTIRE recurring series.
    Use when user says: "удали", "убери совсем", "удали полностью", "удали серию".
    If event_id is an instance (contains '_'): automatically resolves to the parent
    recurring event and deletes the ENTIRE series — not just one occurrence.
    If event_id has no '_': deletes that single non-recurring event.
    Do NOT use for: deleting only one occurrence (→ delete_single_occurrence),
    or only future occurrences (→ delete_future_occurrences).
    """
    try:
        chat_id = get_current_chat_id()
        deleted_id = gcal.delete_event_or_series(chat_id, event_id)
        return f"✅ Событие удалено полностью (id: {deleted_id})."
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при удалении события: {e}"


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
        chat_id = get_current_chat_id()
        result = gcal.delete_this_and_following(chat_id, instance_id)
        if result.get("status") == "deleted single event":
            return "✅ Одиночное событие удалено."
        return f"✅ Это и все последующие повторения удалены. Серия завершена до этой даты."
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при удалении последующих событий: {e}"


@tool
def delete_single_occurrence(instance_id: str) -> str:
    """
    Delete ONE specific occurrence of a recurring event, leaving all others intact.
    instance_id MUST contain underscore (_) — it is the instance ID from get_calendar_events.
    Use when user says: "убрать только в эту пятницу", "отменить встречу 15 марта",
    "пропустить в этот раз", "убрать только сегодня/завтра".
    Do NOT use for: deleting all future occurrences (→ delete_future_occurrences),
    or removing a weekday permanently (→ exclude_recurring_weekday).
    """
    try:
        if '_' not in instance_id:
            return "❌ Это не ID конкретного повторения (нет '_'). Получи список событий и используй instance ID."
        chat_id = get_current_chat_id()
        event = gcal.delete_single_occurrence(chat_id, instance_id)
        summary = event.get('summary', instance_id)
        push_undo(get_conn(), chat_id, 'delete_occurrence', instance_id, summary, get_current_session_id())
        return f"✅ Повторение «{summary}» отменено. Остальные даты серии не изменены."
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при отмене повторения: {e}"


@tool
def exclude_recurring_weekday(event_id: str, weekday: str) -> str:
    """
    Permanently remove a specific weekday from a recurring event's schedule.
    event_id: any instance or parent ID of the recurring series.
    weekday: two-letter code — MO, TU, WE, TH, FR, SA, SU.
    Use when user says: "убрать только по пятницам", "не ставить по выходным навсегда",
    "исключи субботы", "убрать по понедельникам".
    Handles FREQ=DAILY automatically (converts to FREQ=WEEKLY with all days except excluded).
    """
    try:
        chat_id = get_current_chat_id()
        event = gcal.exclude_weekday_from_recurrence(chat_id, event_id, weekday.upper())
        days_ru = {'MO': 'понедельники', 'TU': 'вторники', 'WE': 'среды',
                   'TH': 'четверги', 'FR': 'пятницы', 'SA': 'субботы', 'SU': 'воскресенья'}
        day_name = days_ru.get(weekday.upper(), weekday)
        return f"✅ {event.get('summary', 'Событие')} — {day_name} исключены из расписания навсегда."
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except ValueError as e:
        return f"❌ {e}"
    except Exception as e:
        return f"❌ Ошибка при изменении расписания: {e}"
