import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


async def check_event_task_reminders(bot) -> None:
    """Send notifications for events with linked tasks starting in ~4 hours."""
    from db.database import get_conn
    from db.models import (
        list_connected_users,
        get_pending_event_task_links,
        mark_event_task_links_notified,
        cleanup_old_event_task_links,
        get_setting,
    )

    conn = get_conn()
    now = datetime.now(timezone.utc)
    window_start = (now + timedelta(hours=3, minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    window_end = (now + timedelta(hours=4, minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')

    links = get_pending_event_task_links(conn, window_start, window_end)
    if not links:
        cleanup_old_event_task_links(conn)
        return

    connected = set(list_connected_users(conn))

    # Group by (chat_id, event_id, event_summary, event_start_utc)
    groups: dict[tuple, list] = {}
    for row in links:
        if row["chat_id"] not in connected:
            continue
        key = (row["chat_id"], row["event_id"], row["event_summary"], row["event_start_utc"])
        groups.setdefault(key, []).append(row)

    for (chat_id, event_id, event_summary, event_start_utc), rows in groups.items():
        try:
            tz_offset = int(get_setting(conn, chat_id, 'timezone_offset') or 3)
            event_dt = datetime.strptime(event_start_utc, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
            local_time = (event_dt + timedelta(hours=tz_offset)).strftime('%H:%M')

            task_lines = "\n".join(f"• {r['task_title']}" for r in rows)
            text = (
                f"📋 <b>Через ~4 часа: {event_summary}</b> ({local_time})\n\n"
                f"Привязанные задачи:\n{task_lines}"
            )

            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            mark_event_task_links_notified(conn, [r["id"] for r in rows])
        except Exception as e:
            logger.error("event_task_notifier: failed for chat_id=%s: %s", chat_id, e)

    cleanup_old_event_task_links(conn)
