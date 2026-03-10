import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from langchain_core.tools import tool
from services import google_calendar as gcal
from agent.context import get_current_chat_id

logger = logging.getLogger(__name__)


@tool
def batch_delete_events(event_ids: list[str]) -> str:
    """
    Delete multiple Google Calendar events at once.
    event_ids: list of event ID strings, e.g. ["id1", "id2", "id3"]
    Use this for deleting 1 or more events by ID.
    Works for single events AND recurring event instances.
    Pass a list even for one event: ["event_id_here"]
    """
    try:
        chat_id = get_current_chat_id()
        deleted = []
        errors = []
        for event_id in event_ids:
            try:
                logger.info(f"Deleting event id={event_id!r}")
                gcal.delete_event(chat_id, event_id)
                deleted.append(event_id)
                logger.info(f"Deleted event id={event_id!r} OK")
            except Exception as e:
                logger.warning(f"Failed to delete event id={event_id!r}: {e}")
                errors.append(f"{event_id}: {e}")
        result = f"✅ Удалено событий: {len(deleted)}"
        if errors:
            result += f"\n⚠️ Ошибки при удалении: {'; '.join(errors)}"
        return result
    except Exception as e:
        logger.error(f"batch_delete_events outer error: {e}")
        return f"❌ Ошибка при пакетном удалении: {e}"


@tool
def deduplicate_recurring_events(summary: str) -> str:
    """
    Find and delete duplicate recurring event SERIES with the same name.
    Use when user says "убери дубли Дейлика", "удали дублирование", "два одинаковых события".
    summary: exact event name to deduplicate (e.g. "Дейлик").

    Correctly handles the case where two recurring series produce same-named events every day.
    Deletes the ENTIRE extra series (by parent recurringEventId), not just individual instances.
    Keeps the series that has the most occurrences in the next 30 days.
    """
    try:
        chat_id = get_current_chat_id()
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=30)
        events = gcal.list_events(chat_id, now.isoformat(), end.isoformat(), single_events=True)

        # Count occurrences per recurringEventId (or event id for non-recurring)
        series_count: dict[str, int] = defaultdict(int)
        series_summary: dict[str, str] = {}
        for e in events:
            if e.get('summary', '').strip().lower() != summary.strip().lower():
                continue
            key = e.get('recurringEventId') or e.get('id')
            series_count[key] += 1
            series_summary[key] = e.get('summary', summary)

        if len(series_count) <= 1:
            return f"Дублей «{summary}» не найдено — только одна серия в ближайшие 30 дней."

        # Keep the series with the most occurrences; delete the rest
        sorted_series = sorted(series_count.items(), key=lambda x: -x[1])
        keep_id, keep_count = sorted_series[0]
        to_delete = sorted_series[1:]

        deleted_series = []
        errors = []
        for series_id, count in to_delete:
            try:
                gcal.delete_event(chat_id, series_id)
                deleted_series.append(f"{series_summary.get(series_id, series_id)} ({count} вхождений)")
                logger.info(f"Deleted duplicate series id={series_id!r} ({count} occurrences)")
            except Exception as e:
                logger.warning(f"Failed to delete series id={series_id!r}: {e}")
                errors.append(f"{series_id}: {e}")

        result = f"✅ Удалено {len(deleted_series)} лишних серий «{summary}»:\n"
        result += "\n".join(f"• {s}" for s in deleted_series)
        result += f"\nОставлена серия с {keep_count} вхождениями."
        if errors:
            result += f"\n⚠️ Ошибки: {'; '.join(errors)}"
        return result
    except Exception as e:
        logger.error(f"deduplicate_recurring_events error: {e}")
        return f"❌ Ошибка при удалении дублей: {e}"
