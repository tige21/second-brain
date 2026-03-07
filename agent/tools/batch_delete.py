from langchain_core.tools import tool
from services import google_calendar as gcal


@tool
def batch_delete_events(event_ids: list[str]) -> str:
    """
    Delete multiple Google Calendar events at once.
    event_ids: list of event ID strings, e.g. ["id1", "id2", "id3"]
    Use this when deleting 2 or more events to avoid multiple tool calls.
    """
    try:
        deleted = []
        errors = []
        for event_id in event_ids:
            try:
                gcal.delete_event(event_id)
                deleted.append(event_id)
            except Exception as e:
                errors.append(f"{event_id}: {e}")
        result = f"✅ Удалено событий: {len(deleted)}"
        if errors:
            result += f"\n⚠️ Ошибки: {'; '.join(errors)}"
        return result
    except Exception as e:
        return f"Ошибка при пакетном удалении: {e}"
