from langchain_core.tools import tool
from db.database import get_conn
from db.models import save_reminder
from agent.context import get_current_chat_id


@tool
def set_reminder(text: str, remind_at_utc: str) -> str:
    """
    Set a one-time reminder that fires at the specified time.
    text: what to remind about (use user's exact words).
    remind_at_utc: ISO 8601 UTC, e.g. "2024-01-15T14:30:00Z". Apply Правило 1 for UTC conversion.
    Use when user says: "напомни", "напоминание", "не дай забыть", "через X минут".
    """
    try:
        chat_id = get_current_chat_id()
        conn = get_conn()
        rid = save_reminder(conn, chat_id, text, remind_at_utc)
        return f"✅ Напоминание установлено (id: {rid}): «{text}» в {remind_at_utc}"
    except Exception as e:
        return f"❌ Ошибка при установке напоминания: {e}"
