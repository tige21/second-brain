from datetime import datetime, timezone, timedelta
from services import google_calendar as gcal
from services.yandex_geocoder import geocode_address, get_travel_time_minutes
from config import DEFAULT_TRAVEL_MINUTES

BUFFER_MINUTES = 20  # notify this many minutes before needed departure time


async def _check_for_user(bot, chat_id: int) -> None:
    from db.database import get_conn
    from db.models import get_setting, get_address, is_notified, mark_notified, cleanup_old_notified

    conn = get_conn()
    cleanup_old_notified(conn, chat_id, days=7)
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=5)

    try:
        events = gcal.list_events(chat_id, now.isoformat(), window_end.isoformat())
    except Exception:
        return

    events_with_location = [e for e in events if e.get('location')]
    if not events_with_location:
        return

    active_name = get_setting(conn, chat_id, 'active_address') or ''
    active_addr = get_address(conn, chat_id, active_name) if active_name else None
    origin_coords = active_addr['coords'] if active_addr else None

    for event in events_with_location:
        event_id = event.get('id')
        if is_notified(conn, chat_id, event_id):
            continue

        start_str = event.get('start', {}).get('dateTime')
        if not start_str:
            continue

        try:
            event_start = datetime.fromisoformat(start_str.replace('Z', '+00:00')).astimezone(timezone.utc)
        except Exception:
            continue

        # Skip events that already started more than 15 min ago
        if (now - event_start).total_seconds() > 15 * 60:
            continue

        destination = event.get('location', '')
        driving_minutes = DEFAULT_TRAVEL_MINUTES
        transit_minutes = int(DEFAULT_TRAVEL_MINUTES * 1.5)
        is_estimate = True

        if origin_coords:
            try:
                dest_geo = await geocode_address(destination)
                if dest_geo:
                    dest_coords = f"{dest_geo['lat']},{dest_geo['lon']}"
                    driving_minutes = await get_travel_time_minutes(origin_coords, dest_coords, mode="driving")
                    transit_minutes = int(driving_minutes * 1.5)
                    is_estimate = False
            except Exception:
                pass

        # Use worst case (transit) for departure planning
        worst_case_minutes = max(driving_minutes, transit_minutes)
        depart_at = event_start - timedelta(minutes=worst_case_minutes + BUFFER_MINUTES)
        minutes_until_depart = (depart_at - now).total_seconds() / 60

        # Fire within the 15-min window around the calculated departure time
        if not (-15 <= minutes_until_depart <= 125):
            continue

        tz_offset = int(get_setting(conn, chat_id, 'timezone_offset') or 3)
        local_start = event_start + timedelta(hours=tz_offset)
        local_depart = depart_at + timedelta(hours=tz_offset)
        start_str_fmt = local_start.strftime('%H:%M')
        depart_str_fmt = local_depart.strftime('%H:%M')
        summary = event.get('summary', 'Событие')

        transit_label = " (оценка)" if is_estimate else " (оценка)"
        text = (
            f"🚀 <b>Пора выходить на «{summary}»</b>\n\n"
            f"📍 Начало в {start_str_fmt}\n"
            f"⏰ Выйти в <b>{depart_str_fmt}</b>\n\n"
            f"🚗 На такси: ~{driving_minutes} мин\n"
            f"🚌 Транспорт: ~{transit_minutes} мин{transit_label}\n\n"
            f"📌 {destination}"
        )

        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        mark_notified(conn, chat_id, event_id)


async def check_departures(bot) -> None:
    """Check upcoming events with location for all connected users."""
    from db.database import get_conn
    from db.models import list_connected_users

    conn = get_conn()
    for chat_id in list_connected_users(conn):
        try:
            await _check_for_user(bot, chat_id)
        except Exception:
            pass
