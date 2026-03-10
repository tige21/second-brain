from datetime import datetime, timezone, timedelta
from services import google_calendar as gcal, google_tasks as gtasks


def _format_time(dt_str: str, tz_offset: int = 3) -> str:
    """Convert UTC ISO string to local time HH:MM."""
    if not dt_str:
        return "весь день"
    try:
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            local = dt + timedelta(hours=tz_offset)
            return local.strftime('%H:%M')
        return "весь день"
    except Exception:
        return dt_str


async def _send_for_user(bot, chat_id: int) -> None:
    from db.database import get_conn
    from db.models import get_setting

    conn = get_conn()
    tz_offset = int(get_setting(conn, chat_id, 'timezone_offset') or 3)

    now_utc = datetime.now(timezone.utc)
    local_now = now_utc + timedelta(hours=tz_offset)

    months_ru = [
        '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ]
    date_str = f"{local_now.day} {months_ru[local_now.month]}"

    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = local_midnight - timedelta(hours=tz_offset)
    day_end = day_start + timedelta(days=1)

    try:
        events = gcal.list_events(chat_id, day_start.isoformat(), day_end.isoformat())
    except Exception:
        events = []

    try:
        all_tasks = gtasks.list_tasks(chat_id)
        today_date = local_now.strftime('%Y-%m-%d')
        tasks_today = [t for t in all_tasks if t.get('due', '').startswith(today_date)]
        tasks_no_due = [t for t in all_tasks if not t.get('due')]
    except Exception:
        tasks_today = []
        tasks_no_due = []

    lines = [f"📅 <b>Сводка на {date_str}</b>\n"]

    if events:
        lines.append("🗓 <b>События:</b>")
        for e in events:
            start = e.get('start', {})
            time_str = _format_time(
                start.get('dateTime') or start.get('date', ''), tz_offset
            )
            summary = e.get('summary', 'Без названия')
            lines.append(f"• {time_str} — {summary}")
    else:
        lines.append("🗓 Событий нет")

    lines.append("")

    if tasks_today or tasks_no_due:
        lines.append("✅ <b>Задачи:</b>")
        for t in tasks_today:
            lines.append(f"• {t.get('title', '')}")
        if tasks_no_due:
            lines.append("  <i>без срока:</i>")
            for t in tasks_no_due:
                lines.append(f"• {t.get('title', '')}")
    else:
        lines.append("✅ Задач на сегодня нет")

    await bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="HTML")


async def send_morning_summary(bot) -> None:
    """Send daily morning summary to all connected users."""
    from db.database import get_conn
    from db.models import list_connected_users

    conn = get_conn()
    for chat_id in list_connected_users(conn):
        try:
            await _send_for_user(bot, chat_id)
        except Exception:
            pass
