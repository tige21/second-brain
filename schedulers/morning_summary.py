from datetime import datetime, timezone, timedelta
from services import google_calendar as gcal, google_tasks as gtasks
from config import TELEGRAM_CHAT_ID


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


async def send_morning_summary(bot) -> None:
    """Send daily morning summary to the user."""
    from db.database import get_conn
    from db.models import get_setting

    conn = get_conn()
    tz_offset = int(get_setting(conn, 'timezone_offset') or 3)

    now_utc = datetime.now(timezone.utc)
    local_now = now_utc + timedelta(hours=tz_offset)

    # Localized date string
    months_ru = [
        '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ]
    date_str = f"{local_now.day} {months_ru[local_now.month]}"

    # Today's events (UTC window)
    day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    try:
        events = gcal.list_events(day_start.isoformat(), day_end.isoformat())
    except Exception:
        events = []

    # Tasks due today
    try:
        all_tasks = gtasks.list_tasks()
        today_date = local_now.strftime('%Y-%m-%d')
        tasks = [t for t in all_tasks if t.get('due', '').startswith(today_date)]
    except Exception:
        tasks = []

    # Format HTML message
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

    if tasks:
        lines.append("✅ <b>Задачи на сегодня:</b>")
        for t in tasks:
            lines.append(f"• {t.get('title', '')}")
    else:
        lines.append("✅ Задач на сегодня нет")

    text = "\n".join(lines)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="HTML")
