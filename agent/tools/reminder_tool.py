from langchain_core.tools import tool
from db.database import get_conn
from db.models import save_reminder, get_setting
from agent.context import get_current_chat_id
from agent.tools.calendar_tool import _to_utc
from config import TIMEZONE_OFFSET


@tool
def set_reminder(text: str, remind_at_local: str) -> str:
    """
    Set a one-time reminder that fires at the specified time.
    text: what to remind about (use user's exact words).
    remind_at_local: LOCAL time WITHOUT timezone suffix, e.g. "2026-03-18T14:30:00".
      Conversion to UTC is done automatically. Do NOT subtract the timezone offset yourself.
    Use when user says: "напомни", "напоминание", "не дай забыть", "через X минут".
    """
    try:
        chat_id = get_current_chat_id()
        conn = get_conn()
        tz_offset = int(get_setting(conn, chat_id, 'timezone_offset') or TIMEZONE_OFFSET)
        remind_at_utc = _to_utc(remind_at_local, tz_offset)
        rid = save_reminder(conn, chat_id, text, remind_at_utc)
        return f"✅ Напоминание установлено (id: {rid}): «{text}» в {remind_at_utc}"
    except Exception as e:
        return f"❌ Ошибка при установке напоминания: {e}"
