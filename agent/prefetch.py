import json
from datetime import datetime, timezone, timedelta
from services import google_calendar as gcal
from services import google_tasks as gtasks


def prefetch_context(chat_id: int, tz_offset: int = 3) -> dict[str, str]:
    """
    Fetch today+tomorrow events and all active tasks before calling agent.
    Returns dict with 'today_events' and 'today_tasks' as JSON strings.
    Both calls are fault-tolerant — errors return descriptive strings.
    """
    today_events_str = "нет событий"
    today_tasks_str = "нет задач"

    try:
        now_utc = datetime.now(timezone.utc)
        local_now = now_utc + timedelta(hours=tz_offset)
        local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        fetch_start = local_midnight - timedelta(hours=tz_offset)
        fetch_end = fetch_start + timedelta(days=2)
        events = gcal.list_events(chat_id, fetch_start.isoformat(), fetch_end.isoformat(), single_events=True)
        simplified = []
        seen_ids: set[str] = set()
        for e in events:
            eid = e.get('id', '')
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            raw_start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date")
            raw_end = e.get("end", {}).get("dateTime") or e.get("end", {}).get("date")
            # Convert to local time so agent doesn't need to do UTC math
            start_local = None
            if raw_start and 'T' in raw_start:
                dt = datetime.fromisoformat(raw_start.replace('Z', '+00:00')).astimezone(timezone.utc)
                start_local = (dt + timedelta(hours=tz_offset)).strftime('%Y-%m-%dT%H:%M:%S')
            simplified.append({
                "id": eid,
                "summary": e.get("summary", ""),
                "start": raw_start,
                "start_local": start_local or raw_start,
                "end": raw_end,
                "location": e.get("location"),
                "recurringEventId": e.get("recurringEventId"),
            })
        today_events_str = json.dumps(simplified, ensure_ascii=False) if simplified else "нет событий"
    except Exception as e:
        today_events_str = f"ошибка загрузки: {e}"

    try:
        tasks = gtasks.list_tasks(chat_id)
        simplified_tasks = []
        seen_task_ids: set[str] = set()
        for t in tasks:
            tid = t.get('id', '')
            if tid in seen_task_ids:
                continue
            seen_task_ids.add(tid)
            simplified_tasks.append({
                "id": tid,
                "title": t.get("title", ""),
                "due": t.get("due"),
                "notes": t.get("notes"),
            })
        today_tasks_str = json.dumps(simplified_tasks, ensure_ascii=False) if simplified_tasks else "нет задач"
    except Exception as e:
        today_tasks_str = f"ошибка загрузки: {e}"

    return {
        "today_events": today_events_str,
        "today_tasks": today_tasks_str,
    }
