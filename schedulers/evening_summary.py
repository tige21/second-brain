from datetime import datetime, timezone, timedelta
from services import google_calendar as gcal, google_tasks as gtasks


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

    local_tomorrow = (local_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    tmrw_start_utc = local_tomorrow - timedelta(hours=tz_offset)
    tmrw_end_utc = tmrw_start_utc + timedelta(days=1)

    try:
        tomorrow_events = gcal.list_events(
            chat_id, tmrw_start_utc.isoformat(), tmrw_end_utc.isoformat(), single_events=True
        )
    except Exception:
        tomorrow_events = []

    try:
        all_tasks = gtasks.list_tasks(chat_id, show_completed=True)
        today_date = local_now.strftime('%Y-%m-%d')
        pending = [t for t in all_tasks if t.get('status') != 'completed' and t.get('due', '').startswith(today_date)]
        completed = [t for t in all_tasks if t.get('status') == 'completed']
    except Exception:
        pending = []
        completed = []

    date_str = f"{local_tomorrow.day} {months_ru[local_tomorrow.month]}"
    lines = ["🌆 <b>Вечерняя сводка</b>\n"]

    lines.append(f"📅 <b>Завтра, {date_str}:</b>")
    if tomorrow_events:
        for e in tomorrow_events:
            start = e.get('start', {})
            dt_str = start.get('dateTime') or start.get('date', '')
            if 'T' in dt_str:
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                time_str = (dt + timedelta(hours=tz_offset)).strftime('%H:%M')
            else:
                time_str = "весь день"
            lines.append(f"⏰ <b>{time_str}</b>  {e.get('summary', 'Без названия')}")
    else:
        lines.append("Событий нет")

    lines.append("")

    if pending:
        lines.append("⏳ <b>Не сделано сегодня:</b>")
        for t in pending:
            lines.append(f"☐ {t.get('title', '')}")
    else:
        lines.append("✅ Все задачи на сегодня выполнены!")

    if completed:
        lines.append("")
        lines.append(f"✅ <b>Выполнено сегодня:</b> {len(completed)}")

    await bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="HTML")


async def send_evening_summary(bot) -> None:
    """Send evening summary to all connected users."""
    from db.database import get_conn
    from db.models import list_connected_users

    conn = get_conn()
    for chat_id in list_connected_users(conn):
        try:
            await _send_for_user(bot, chat_id)
        except Exception:
            pass
