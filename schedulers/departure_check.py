from datetime import datetime, timezone, timedelta
from services import google_calendar as gcal
from services.yandex_geocoder import geocode_address, get_travel_time_minutes
from config import TELEGRAM_CHAT_ID, DEFAULT_TRAVEL_MINUTES


async def check_departures(bot) -> None:
    """Check upcoming events with location and send departure alerts."""
    from db.database import get_conn
    from db.models import get_setting, get_address, is_notified, mark_notified

    conn = get_conn()
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=5)

    # Get upcoming events with location field
    try:
        events = gcal.list_events(now.isoformat(), window_end.isoformat())
    except Exception:
        return

    events_with_location = [e for e in events if e.get('location')]
    if not events_with_location:
        return

    # Get active address coords
    active_name = get_setting(conn, 'active_address') or ''
    active_addr = get_address(conn, active_name) if active_name else None
    origin_coords = active_addr['coords'] if active_addr else None

    for event in events_with_location:
        event_id = event.get('id')
        if is_notified(conn, event_id):
            continue

        start_str = event.get('start', {}).get('dateTime')
        if not start_str:
            continue

        try:
            event_start = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        except Exception:
            continue

        # Skip events started more than 15 min ago
        if (now - event_start).total_seconds() > 15 * 60:
            continue

        destination = event.get('location', '')
        travel_minutes = DEFAULT_TRAVEL_MINUTES
        is_estimate = True

        if origin_coords:
            try:
                dest_geo = await geocode_address(destination)
                if dest_geo:
                    dest_coords = f"{dest_geo['lat']},{dest_geo['lon']}"
                    travel_minutes = await get_travel_time_minutes(origin_coords, dest_coords)
                    is_estimate = False
            except Exception:
                pass  # fallback to DEFAULT_TRAVEL_MINUTES

        buffer_minutes = 10
        depart_at = event_start - timedelta(minutes=travel_minutes + buffer_minutes)
        minutes_until_depart = (depart_at - now).total_seconds() / 60

        # Send alert if within window
        if not (-15 <= minutes_until_depart <= 125):
            continue

        tz_offset = int(get_setting(conn, 'timezone_offset') or 3)
        local_start = event_start + timedelta(hours=tz_offset)
        time_str = local_start.strftime('%H:%M')
        summary = event.get('summary', 'Событие')

        if minutes_until_depart > 0:
            depart_label = f"через ~{int(minutes_until_depart)} мин"
        else:
            depart_label = "прямо сейчас"

        estimate_label = " (оценка)" if is_estimate else ""
        text = (
            f"🚀 <b>Пора выходить!</b> (от: {active_name or 'текущее место'})\n\n"
            f"📍 {summary}\n"
            f"🕐 Начало в {time_str}\n"
            f"⏰ Выходить {depart_label}\n"
            f"🚗 В пути ~{travel_minutes} мин{estimate_label}\n"
            f"📍 {destination}"
        )

        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="HTML")
        mark_notified(conn, event_id)
