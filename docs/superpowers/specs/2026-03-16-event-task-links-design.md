# Event-Task Links Design

**Date:** 2026-03-16
**Feature:** Link Google Tasks to Calendar Events with pre-event notifications

## Overview

Allow users to attach tasks to calendar events via natural language. Four hours before the event, the bot sends a Telegram notification listing all linked tasks.

**Example flow:**
1. User: "добавь к событию занятие по инглишу задачу сделать домашку"
2. Agent resolves event via `get_calendar_events`, calls `create_task_for_event`
3. Bot creates the task in Google Tasks + stores the link in SQLite
4. ~4 hours before the event, scheduler detects the link and sends Telegram notification

## Database

New table `event_task_links` added inside the top-level `executescript` block in `db/database.py`'s `_run_migrations` — NOT in the `if 'addresses' not in tables` branch (which only runs on legacy installs). This ensures the table is created on every startup via `CREATE TABLE IF NOT EXISTS`.

```sql
CREATE TABLE IF NOT EXISTS event_task_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    event_summary TEXT NOT NULL,
    event_start_utc TEXT NOT NULL,
    task_title TEXT NOT NULL,
    notified INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_event_task_links_pending
    ON event_task_links (notified, event_start_utc);
```

`notified` flag prevents duplicate notifications across scheduler runs.

CRUD functions added to `db/models.py`:

- `add_event_task_link(conn, chat_id, event_id, task_id, event_summary, event_start_utc, task_title) -> None`
- `get_pending_event_task_links(conn, window_start_utc, window_end_utc) -> list[dict]`
  — returns all unnotified links where `event_start_utc` falls within the window.
  — each row dict includes: `id`, `chat_id`, `event_id`, `event_summary`, `event_start_utc`, `task_title`
- `mark_event_task_links_notified(conn, ids: list[int]) -> None` — sets `notified = 1` for given row IDs
- `cleanup_old_event_task_links(conn, days: int = 7) -> None` — deletes rows where `notified = 1` and `created_at < now - days`

## Agent Tool

New `create_task_for_event` function added to `agent/tools/tasks_tool.py` as a **synchronous** `@tool` (matching all existing tools in that file — no `async def`).

**Parameters:**
- `event_id: str` — calendar event ID (resolved by agent via `get_calendar_events`)
- `event_summary: str` — event title (for storing in link record)
- `event_start_utc: str` — event start in ISO 8601 UTC (e.g. `"2024-03-19T09:50:00Z"`)
- `title: str` — task title (user's exact words)
- `notes: str = None` — optional extra notes

**`due` date handling:** `event_start_utc` must be truncated to the date portion and formatted as `YYYY-MM-DDT00:00:00Z` before passing to `gtasks.create_task`. Example: `"2024-03-19T09:50:00Z"` → `"2024-03-19T00:00:00Z"`. This is required by the Google Tasks API.

**Behavior:**
1. Derive `due = event_start_utc[:10] + "T00:00:00Z"`
2. Call `gtasks.create_task(chat_id, title, due, notes)` — standard positional args matching the existing service signature
3. On success, call `add_event_task_link(conn, chat_id, event_id, task_id, event_summary, event_start_utc, title)`
4. If step 3 raises an exception: log the error, attempt `gtasks.delete_task(chat_id, task_id)` to avoid orphaned task, then return an error message to the agent
5. On full success, call `push_undo(conn, chat_id, 'create_task', task['id'], title, session_id)`
6. Return confirmation message

**Tool docstring trigger phrases** (in English for LangChain routing):
```
Use when user says: "добавь задачу к событию", "привяжи задачу к встрече",
"к этому событию нужно сделать X", "добавь к встрече задачу".
Do NOT use create_task when the user links a task to a calendar event — use
create_task_for_event instead to ensure the notification link is stored.
```

Registered in `TOOLS` list in `agent/executor.py`.

## Scheduler

New file `schedulers/event_task_notifier.py`.

**Schedule:** every 15 minutes (same interval as `departure_check`).

**Window:** events starting between `now + 3.5h` and `now + 4.5h` (± 30 min around 4-hour mark).

**Logic:**
1. Get `now` in UTC
2. Compute `window_start = now + 3.5h`, `window_end = now + 4.5h`
3. Call `get_pending_event_task_links(conn, window_start, window_end)`
4. Get connected users via `list_connected_users(conn)` — filter results to only include `chat_id` values present in the connected users list; skip any others
5. Group results by `(chat_id, event_id, event_summary, event_start_utc)`
6. For each group:
   - Derive local time: `event_start_utc` + `int(get_setting(conn, chat_id, 'timezone_offset') or 3)` hours
   - Format local time as `HH:MM`
   - Send Telegram message:
     ```
     📋 Через ~4 часа: {event_summary} ({local_time})

     Привязанные задачи:
     • {task_title_1}
     • {task_title_2}
     ```
   - Call `mark_event_task_links_notified(conn, [row['id'] for row in group])`
7. After notification loop, call `cleanup_old_event_task_links(conn, days=7)` to prune stale rows
8. Wrap each user's processing in try/except — log errors, never let one user's failure affect others

Registered in `main.py` alongside existing jobs:
```python
scheduler.add_job(check_event_task_reminders, 'interval', minutes=15)
```

## Files Changed

| File | Change |
|------|--------|
| `db/database.py` | Add `event_task_links` table + index in `executescript` block |
| `db/models.py` | Add 4 CRUD functions |
| `agent/tools/tasks_tool.py` | Add `create_task_for_event` tool (sync) |
| `agent/executor.py` | Register new tool in `TOOLS` |
| `schedulers/event_task_notifier.py` | New scheduler file |
| `main.py` | Register new APScheduler job |

## What Does NOT Change

- All existing tools (`create_task`, `get_tasks`, etc.) are untouched
- Existing scheduler jobs and their intervals are untouched
- `gtasks.create_task` service function is used as-is — no signature changes
- No changes to `agent/executor.py` except adding the tool to `TOOLS`

## Error Handling

- `GoogleAuthExpiredError` → return `_AUTH_ERROR_MSG`
- DB write failure after Google Tasks API success → delete orphaned task, return error
- Event not found / invalid `event_id` → agent returns error, user can retry
- Scheduler per-user failures are caught, logged, do not affect other users
- Duplicate notifications prevented by `notified` flag

## Testing

- Unit test for `create_task_for_event` tool:
  - Happy path: mock `gtasks.create_task`, `add_event_task_link`, `push_undo` — verify all called with correct args
  - `due` truncation: verify `"2024-03-19T09:50:00Z"` → `"2024-03-19T00:00:00Z"`
  - DB failure after task creation: verify orphaned task deletion is attempted
  - `GoogleAuthExpiredError`: verify error message returned
- Unit test for DB functions with in-memory SQLite:
  - `add_event_task_link` + `get_pending_event_task_links` (window matching, notified=0 filter)
  - `mark_event_task_links_notified` (sets flag, others unaffected)
  - `cleanup_old_event_task_links` (deletes old notified rows, keeps recent ones)
- Unit test for scheduler:
  - Mock DB query + `bot.send_message` — verify correct grouping and message format
  - Verify unapproved/disconnected users are skipped
  - Verify `notified` flag is set after send
  - Verify per-user exception does not abort other users
