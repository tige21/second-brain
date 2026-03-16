# Event-Task Links Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to link Google Tasks to Calendar events; send a Telegram notification with all linked tasks ~4 hours before the event.

**Architecture:** New SQLite table `event_task_links` stores the task-event associations. A new LangChain `@tool` creates the task and the link in one call. A new APScheduler job runs every 15 minutes and sends notifications for events starting in 3.5–4.5 hours.

**Tech Stack:** Python 3.11+, SQLite (via stdlib sqlite3), LangChain `@tool`, APScheduler, python-telegram-bot, tenacity (already in use for Google API calls).

**Spec:** `docs/superpowers/specs/2026-03-16-event-task-links-design.md`

---

## Chunk 1: Database — migration + CRUD

### Task 1: Add `event_task_links` table migration

**Files:**
- Modify: `db/database.py` — add table + index inside the top-level `executescript` block (lines 19-51)

- [ ] **Step 1: Write the failing test**

Add to a new file `tests/test_event_task_links_db.py`:

```python
import os
import sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123")
os.environ.setdefault("OPENAI_API_KEY", "x")

from db.database import init_db


@pytest.fixture
def db(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    yield conn
    conn.close()


def test_event_task_links_table_exists(db):
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "event_task_links" in tables


def test_event_task_links_has_index(db):
    indexes = {r[1] for r in db.execute(
        "SELECT * FROM sqlite_master WHERE type='index'"
    ).fetchall()}
    assert "idx_event_task_links_pending" in indexes
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_event_task_links_db.py -v
```
Expected: FAIL — `event_task_links` table not found.

- [ ] **Step 3: Add migration to `db/database.py`**

Inside the `conn.executescript("""...""")` block (the one that starts at line 19), add before the closing `"""`):

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

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_event_task_links_db.py::test_event_task_links_table_exists tests/test_event_task_links_db.py::test_event_task_links_has_index -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add db/database.py tests/test_event_task_links_db.py
git commit -m "feat(no-ref): add event_task_links table and index"
```

---

### Task 2: Add CRUD functions to `db/models.py`

**Files:**
- Modify: `db/models.py` — append 4 functions at the end
- Modify: `tests/test_event_task_links_db.py` — add CRUD tests

- [ ] **Step 1: Write failing tests**

Append to `tests/test_event_task_links_db.py`:

```python
from datetime import datetime, timezone, timedelta


def test_add_and_get_pending_event_task_links(db):
    from db.models import add_event_task_link, get_pending_event_task_links

    now = datetime.now(timezone.utc)
    event_start = now + timedelta(hours=4)
    event_start_str = event_start.strftime('%Y-%m-%dT%H:%M:%SZ')

    add_event_task_link(
        db,
        chat_id=111,
        event_id="evt1",
        task_id="tsk1",
        event_summary="English lesson",
        event_start_utc=event_start_str,
        task_title="Do homework",
    )

    window_start = (now + timedelta(hours=3, minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    window_end = (now + timedelta(hours=4, minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')

    links = get_pending_event_task_links(db, window_start, window_end)
    assert len(links) == 1
    row = links[0]
    assert row["chat_id"] == 111
    assert row["event_id"] == "evt1"
    assert row["task_id"] == "tsk1"
    assert row["event_summary"] == "English lesson"
    assert row["task_title"] == "Do homework"
    assert "id" in row  # required for mark_notified


def test_get_pending_excludes_already_notified(db):
    from db.models import add_event_task_link, get_pending_event_task_links, mark_event_task_links_notified

    now = datetime.now(timezone.utc)
    event_start = now + timedelta(hours=4)
    event_start_str = event_start.strftime('%Y-%m-%dT%H:%M:%SZ')

    add_event_task_link(db, 222, "evt2", "tsk2", "Meeting", event_start_str, "Prepare slides")
    window_start = (now + timedelta(hours=3, minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    window_end = (now + timedelta(hours=4, minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')

    links = get_pending_event_task_links(db, window_start, window_end)
    assert len(links) == 1

    mark_event_task_links_notified(db, [links[0]["id"]])

    links_after = get_pending_event_task_links(db, window_start, window_end)
    assert len(links_after) == 0


def test_get_pending_excludes_outside_window(db):
    from db.models import add_event_task_link, get_pending_event_task_links

    now = datetime.now(timezone.utc)
    # Event 10 hours away — outside 3.5–4.5h window
    event_start = (now + timedelta(hours=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    add_event_task_link(db, 333, "evt3", "tsk3", "Far event", event_start, "Some task")

    window_start = (now + timedelta(hours=3, minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    window_end = (now + timedelta(hours=4, minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')

    links = get_pending_event_task_links(db, window_start, window_end)
    assert len(links) == 0


def test_cleanup_old_event_task_links(db):
    from db.models import add_event_task_link, mark_event_task_links_notified, cleanup_old_event_task_links, get_pending_event_task_links

    now = datetime.now(timezone.utc)
    # Insert an old notified row by backdating created_at manually
    db.execute(
        "INSERT INTO event_task_links "
        "(chat_id, event_id, task_id, event_summary, event_start_utc, task_title, notified, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (444, "evt_old", "tsk_old", "Old event", "2024-01-01T09:00:00Z", "Old task",
         (now - timedelta(days=10)).strftime('%Y-%m-%dT%H:%M:%SZ'))
    )
    db.commit()

    # Also insert a recent notified row — should NOT be deleted
    db.execute(
        "INSERT INTO event_task_links "
        "(chat_id, event_id, task_id, event_summary, event_start_utc, task_title, notified, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (444, "evt_new", "tsk_new", "New event", "2026-03-16T09:00:00Z", "New task",
         now.strftime('%Y-%m-%dT%H:%M:%SZ'))
    )
    db.commit()

    cleanup_old_event_task_links(db, days=7)

    remaining = db.execute(
        "SELECT event_id FROM event_task_links WHERE chat_id = 444"
    ).fetchall()
    event_ids = {r[0] for r in remaining}
    assert "evt_old" not in event_ids
    assert "evt_new" in event_ids
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_event_task_links_db.py -v -k "crud or pending or cleanup or notified"
```
Expected: FAIL — functions not defined.

- [ ] **Step 3: Implement CRUD functions in `db/models.py`**

Append to `db/models.py` after the last function:

```python
# ── Event-task links ──────────────────────────────────────────────────────────

def add_event_task_link(
    conn: sqlite3.Connection,
    chat_id: int,
    event_id: str,
    task_id: str,
    event_summary: str,
    event_start_utc: str,
    task_title: str,
) -> None:
    conn.execute(
        "INSERT INTO event_task_links "
        "(chat_id, event_id, task_id, event_summary, event_start_utc, task_title) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, event_id, task_id, event_summary, event_start_utc, task_title),
    )
    conn.commit()


def get_pending_event_task_links(
    conn: sqlite3.Connection,
    window_start_utc: str,
    window_end_utc: str,
) -> list[dict]:
    rows = conn.execute(
        "SELECT id, chat_id, event_id, task_id, event_summary, event_start_utc, task_title "
        "FROM event_task_links "
        "WHERE notified = 0 AND event_start_utc >= ? AND event_start_utc <= ?",
        (window_start_utc, window_end_utc),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_event_task_links_notified(conn: sqlite3.Connection, ids: list[int]) -> None:
    if not ids:
        return
    placeholders = ','.join(['?'] * len(ids))
    conn.execute(
        f"UPDATE event_task_links SET notified = 1 WHERE id IN ({placeholders})",
        tuple(ids),
    )
    conn.commit()


def cleanup_old_event_task_links(conn: sqlite3.Connection, days: int = 7) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
    conn.execute(
        "DELETE FROM event_task_links WHERE notified = 1 AND created_at < ?",
        (cutoff,),
    )
    conn.commit()
```

- [ ] **Step 4: Run all DB tests to verify they pass**

```bash
pytest tests/test_event_task_links_db.py -v
```
Expected: all PASS.

- [ ] **Step 5: Run full test suite to verify nothing broke**

```bash
pytest tests/ -v --ignore=tests/test_agent_live.py
```
Expected: all existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add db/models.py tests/test_event_task_links_db.py
git commit -m "feat(no-ref): add event_task_links CRUD functions"
```

---

## Chunk 2: Agent tool

### Task 3: Implement `create_task_for_event` tool

**Files:**
- Modify: `agent/tools/tasks_tool.py` — append new tool
- Modify: `agent/executor.py` — add import + register in TOOLS
- Create: `tests/test_create_task_for_event.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_create_task_for_event.py`:

```python
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123")
os.environ.setdefault("OPENAI_API_KEY", "x")


@pytest.fixture
def db(tmp_path):
    from db.database import init_db
    conn = init_db(str(tmp_path / "test.db"))
    yield conn


def test_due_date_truncation():
    """event_start_utc with time component must be truncated to 00:00:00Z."""
    from agent.tools.tasks_tool import create_task_for_event

    created_task = {"id": "task_abc", "title": "Do homework"}
    mock_conn = MagicMock()

    with patch("agent.tools.tasks_tool.get_current_chat_id", return_value=111), \
         patch("agent.tools.tasks_tool.get_current_session_id", return_value="sess1"), \
         patch("agent.tools.tasks_tool.get_conn", return_value=mock_conn), \
         patch("agent.tools.tasks_tool.gtasks.create_task", return_value=created_task) as mock_create, \
         patch("agent.tools.tasks_tool.add_event_task_link") as mock_link, \
         patch("agent.tools.tasks_tool.push_undo"):

        result = create_task_for_event.invoke({
            "event_id": "evt1",
            "event_summary": "English lesson",
            "event_start_utc": "2026-03-18T09:50:00Z",
            "title": "Do homework",
        })

    # due must be truncated to date-only at 00:00:00Z
    mock_create.assert_called_once_with(111, "Do homework", "2026-03-18T00:00:00Z", None)
    assert "✅" in result


def test_link_is_stored(db):
    """After task creation, the link must be persisted in event_task_links."""
    from agent.tools.tasks_tool import create_task_for_event
    from db.models import get_pending_event_task_links
    from datetime import datetime, timezone, timedelta

    created_task = {"id": "task_xyz", "title": "Buy groceries"}

    now = datetime.now(timezone.utc)
    event_start = (now + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%SZ')

    with patch("agent.tools.tasks_tool.get_current_chat_id", return_value=111), \
         patch("agent.tools.tasks_tool.get_current_session_id", return_value="sess1"), \
         patch("agent.tools.tasks_tool.get_conn", return_value=db), \
         patch("agent.tools.tasks_tool.gtasks.create_task", return_value=created_task), \
         patch("agent.tools.tasks_tool.push_undo"):

        create_task_for_event.invoke({
            "event_id": "evt2",
            "event_summary": "Shopping trip",
            "event_start_utc": event_start,
            "title": "Buy groceries",
        })

    window_start = (now + timedelta(hours=3, minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    window_end = (now + timedelta(hours=4, minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    links = get_pending_event_task_links(db, window_start, window_end)
    assert len(links) == 1
    assert links[0]["task_id"] == "task_xyz"
    assert links[0]["task_title"] == "Buy groceries"


def test_orphan_cleanup_on_db_failure():
    """If DB write fails after task creation, the orphaned task must be deleted."""
    from agent.tools.tasks_tool import create_task_for_event

    created_task = {"id": "task_orphan", "title": "Orphan task"}

    with patch("agent.tools.tasks_tool.get_current_chat_id", return_value=111), \
         patch("agent.tools.tasks_tool.get_current_session_id", return_value="sess1"), \
         patch("agent.tools.tasks_tool.get_conn", return_value=MagicMock()), \
         patch("agent.tools.tasks_tool.gtasks.create_task", return_value=created_task), \
         patch("agent.tools.tasks_tool.add_event_task_link", side_effect=Exception("DB error")), \
         patch("agent.tools.tasks_tool.gtasks.delete_task") as mock_delete:

        result = create_task_for_event.invoke({
            "event_id": "evt3",
            "event_summary": "Some event",
            "event_start_utc": "2026-03-18T09:50:00Z",
            "title": "Orphan task",
        })

    mock_delete.assert_called_once_with(111, "task_orphan")
    assert "❌" in result


def test_auth_error_returns_message():
    """GoogleAuthExpiredError must return the standard error message."""
    from agent.tools.tasks_tool import create_task_for_event
    from services.google_auth import GoogleAuthExpiredError

    with patch("agent.tools.tasks_tool.get_current_chat_id", return_value=111), \
         patch("agent.tools.tasks_tool.gtasks.create_task", side_effect=GoogleAuthExpiredError()):

        result = create_task_for_event.invoke({
            "event_id": "evt4",
            "event_summary": "Some event",
            "event_start_utc": "2026-03-18T09:50:00Z",
            "title": "Some task",
        })

    assert "/connect" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_create_task_for_event.py -v
```
Expected: FAIL — `create_task_for_event` not defined.

- [ ] **Step 3: Implement the tool in `agent/tools/tasks_tool.py`**

Add import at the top of `tasks_tool.py` (after existing imports):

```python
from db.models import push_undo, add_event_task_link
from services import google_tasks as gtasks
```

Wait — `gtasks` is already imported as `from services import google_tasks as gtasks`. Check the existing import line and add only `add_event_task_link` to the models import line:

```python
from db.models import push_undo, add_event_task_link
```

Then append the new tool at the end of `agent/tools/tasks_tool.py`:

```python
@tool
def create_task_for_event(
    event_id: str,
    event_summary: str,
    event_start_utc: str,
    title: str,
    notes: str = None,
) -> str:
    """
    Create a Google Task linked to a specific calendar event.
    Use when user says: "добавь задачу к событию", "привяжи задачу к встрече",
    "к этому событию нужно сделать X", "добавь к встрече задачу".
    Do NOT use create_task when the user links a task to a calendar event — use
    create_task_for_event instead to ensure the notification link is stored.
    event_id: calendar event ID (get via get_calendar_events if not known).
    event_summary: event title (from get_calendar_events or conversation context).
    event_start_utc: event start datetime in ISO 8601 UTC, e.g. "2026-03-18T09:50:00Z".
    title: task title (use user's exact words).
    notes: optional extra description.
    The user will receive a Telegram reminder ~4 hours before the event.
    """
    try:
        chat_id = get_current_chat_id()
        due = event_start_utc[:10] + "T00:00:00Z"
        task = gtasks.create_task(chat_id, title, due, notes)
        try:
            conn = get_conn()
            add_event_task_link(
                conn,
                chat_id=chat_id,
                event_id=event_id,
                task_id=task['id'],
                event_summary=event_summary,
                event_start_utc=event_start_utc,
                task_title=title,
            )
            push_undo(conn, chat_id, 'create_task', task['id'], title, get_current_session_id())
        except Exception as db_err:
            import logging
            logging.getLogger(__name__).error(
                "event_task_link DB write failed for task %s: %s", task['id'], db_err
            )
            try:
                gtasks.delete_task(chat_id, task['id'])
            except Exception:
                pass
            return f"❌ Не удалось сохранить привязку задачи к событию: {db_err}"
        return (
            f"✅ Задача создана и привязана к событию «{event_summary}»: "
            f"{title} (id: {task['id']}). Напомню за 4 часа до начала."
        )
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при создании задачи: {e}"
```

- [ ] **Step 4: Register tool in `agent/executor.py`**

In `agent/executor.py`, add the import:
```python
from agent.tools.tasks_tool import get_tasks, create_task, update_task, complete_task, delete_task, create_task_for_event
```

Add `create_task_for_event` to the `TOOLS` list after `delete_task`.

- [ ] **Step 5: Run tool tests to verify they pass**

```bash
pytest tests/test_create_task_for_event.py -v
```
Expected: all 4 PASS.

- [ ] **Step 6: Run full test suite**

```bash
pytest tests/ -v --ignore=tests/test_agent_live.py
```
Expected: all existing tests still PASS.

- [ ] **Step 7: Commit**

```bash
git add agent/tools/tasks_tool.py agent/executor.py tests/test_create_task_for_event.py
git commit -m "feat(no-ref): add create_task_for_event tool with event link storage"
```

---

## Chunk 3: Scheduler

### Task 4: Implement `event_task_notifier` scheduler

**Files:**
- Create: `schedulers/event_task_notifier.py`
- Modify: `main.py` — add import + register job
- Create: `tests/test_event_task_notifier.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_event_task_notifier.py`:

```python
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123")
os.environ.setdefault("OPENAI_API_KEY", "x")


@pytest.fixture
def db(tmp_path):
    from db.database import init_db
    conn = init_db(str(tmp_path / "test.db"))
    yield conn


@pytest.mark.asyncio
async def test_sends_notification_for_pending_link(db):
    """Scheduler sends a message when a linked event is 4 hours away."""
    from db.models import add_event_task_link
    from schedulers.event_task_notifier import check_event_task_reminders

    now = datetime.now(timezone.utc)
    event_start = (now + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%SZ')
    add_event_task_link(db, 111, "evt1", "tsk1", "English lesson", event_start, "Do homework")

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    with patch("schedulers.event_task_notifier.get_conn", return_value=db), \
         patch("schedulers.event_task_notifier.list_connected_users", return_value=[111]), \
         patch("schedulers.event_task_notifier.get_setting", return_value="3"):
        await check_event_task_reminders(mock_bot)

    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args
    assert call_kwargs.kwargs["chat_id"] == 111
    assert "English lesson" in call_kwargs.kwargs["text"]
    assert "Do homework" in call_kwargs.kwargs["text"]


@pytest.mark.asyncio
async def test_marks_notified_after_send(db):
    """After sending, links are marked notified and won't be sent again."""
    from db.models import add_event_task_link, get_pending_event_task_links
    from schedulers.event_task_notifier import check_event_task_reminders

    now = datetime.now(timezone.utc)
    event_start = (now + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%SZ')
    add_event_task_link(db, 111, "evt2", "tsk2", "Meeting", event_start, "Prepare slides")

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    with patch("schedulers.event_task_notifier.get_conn", return_value=db), \
         patch("schedulers.event_task_notifier.list_connected_users", return_value=[111]), \
         patch("schedulers.event_task_notifier.get_setting", return_value="3"):
        await check_event_task_reminders(mock_bot)

    # Run again — should NOT send a second time
    mock_bot.send_message.reset_mock()
    with patch("schedulers.event_task_notifier.get_conn", return_value=db), \
         patch("schedulers.event_task_notifier.list_connected_users", return_value=[111]), \
         patch("schedulers.event_task_notifier.get_setting", return_value="3"):
        await check_event_task_reminders(mock_bot)

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_skips_disconnected_users(db):
    """Links for users not in list_connected_users are skipped."""
    from db.models import add_event_task_link
    from schedulers.event_task_notifier import check_event_task_reminders

    now = datetime.now(timezone.utc)
    event_start = (now + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%SZ')
    # chat_id=999 is not in connected users
    add_event_task_link(db, 999, "evt3", "tsk3", "Secret meeting", event_start, "Hidden task")

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    with patch("schedulers.event_task_notifier.get_conn", return_value=db), \
         patch("schedulers.event_task_notifier.list_connected_users", return_value=[111]), \
         patch("schedulers.event_task_notifier.get_setting", return_value="3"):
        await check_event_task_reminders(mock_bot)

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_groups_multiple_tasks_per_event(db):
    """Multiple tasks linked to the same event are grouped in one message."""
    from db.models import add_event_task_link
    from schedulers.event_task_notifier import check_event_task_reminders

    now = datetime.now(timezone.utc)
    event_start = (now + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%SZ')
    add_event_task_link(db, 111, "evt4", "tsk4a", "Workshop", event_start, "Buy materials")
    add_event_task_link(db, 111, "evt4", "tsk4b", "Workshop", event_start, "Print handouts")

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    with patch("schedulers.event_task_notifier.get_conn", return_value=db), \
         patch("schedulers.event_task_notifier.list_connected_users", return_value=[111]), \
         patch("schedulers.event_task_notifier.get_setting", return_value="3"):
        await check_event_task_reminders(mock_bot)

    # Only one message for both tasks
    assert mock_bot.send_message.call_count == 1
    text = mock_bot.send_message.call_args.kwargs["text"]
    assert "Buy materials" in text
    assert "Print handouts" in text


@pytest.mark.asyncio
async def test_one_user_failure_does_not_abort_others(db):
    """If sending to one user fails, other users still get notified."""
    from db.models import add_event_task_link
    from schedulers.event_task_notifier import check_event_task_reminders

    now = datetime.now(timezone.utc)
    event_start = (now + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%SZ')
    add_event_task_link(db, 111, "evt5a", "tsk5a", "Event A", event_start, "Task A")
    add_event_task_link(db, 222, "evt5b", "tsk5b", "Event B", event_start, "Task B")

    send_call_count = 0

    async def send_side_effect(**kwargs):
        nonlocal send_call_count
        if kwargs["chat_id"] == 111:
            raise Exception("Telegram error")
        send_call_count += 1

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(side_effect=send_side_effect)

    with patch("schedulers.event_task_notifier.get_conn", return_value=db), \
         patch("schedulers.event_task_notifier.list_connected_users", return_value=[111, 222]), \
         patch("schedulers.event_task_notifier.get_setting", return_value="3"):
        await check_event_task_reminders(mock_bot)

    assert send_call_count == 1  # user 222 received their notification
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_event_task_notifier.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `schedulers/event_task_notifier.py`**

Create `schedulers/event_task_notifier.py`:

```python
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

    # Group by (chat_id, event_id)
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
```

- [ ] **Step 4: Register scheduler in `main.py`**

Add import at the top of `main.py` with the other scheduler imports:
```python
from schedulers.event_task_notifier import check_event_task_reminders
```

Add job after the departure_check job:
```python
    # Event-task reminders: every 15 minutes
    scheduler.add_job(
        check_event_task_reminders,
        'interval',
        minutes=15,
        id='event_task_reminders',
        args=[app.bot],
    )
```

- [ ] **Step 5: Add `pytest-asyncio` dependency and config**

Add to `requirements.txt`:
```
pytest-asyncio>=0.23
```

Install:
```bash
pip install pytest-asyncio>=0.23
```

Create `pytest.ini` in the project root:
```ini
[pytest]
asyncio_mode = auto
```

This makes all `async def test_*` functions run automatically as asyncio tests — no per-test decorator needed. The `@pytest.mark.asyncio` decorators already in the test file are harmless with this setting.

- [ ] **Step 6: Run scheduler tests to verify they pass**

```bash
pytest tests/test_event_task_notifier.py -v
```
Expected: all 5 PASS.

- [ ] **Step 7: Run full test suite**

```bash
pytest tests/ -v --ignore=tests/test_agent_live.py
```
Expected: all tests PASS. No regressions.

- [ ] **Step 8: Commit**

```bash
git add schedulers/event_task_notifier.py main.py tests/test_event_task_notifier.py pytest.ini requirements.txt
git commit -m "feat(no-ref): add event_task_notifier scheduler with 4-hour pre-event alerts"
```

---

## Final verification

- [ ] **Run the full test suite one last time**

```bash
pytest tests/ -v --ignore=tests/test_agent_live.py
```
Expected: all tests PASS.

- [ ] **Manually verify bot behavior** (optional, requires credentials)

1. Create a calendar event for ~4 hours from now
2. Tell the bot: "добавь к событию [name] задачу [task]"
3. Verify the agent calls `create_task_for_event` (not `create_task`)
4. Check the task appears in Google Tasks with correct due date
5. Wait for the scheduler window or trigger manually: `python -c "import asyncio; from schedulers.event_task_notifier import check_event_task_reminders; ..."`
