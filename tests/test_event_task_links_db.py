import os
import sys
import pytest
from datetime import datetime, timezone, timedelta
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
    event_start = (now + timedelta(hours=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    add_event_task_link(db, 333, "evt3", "tsk3", "Far event", event_start, "Some task")

    window_start = (now + timedelta(hours=3, minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    window_end = (now + timedelta(hours=4, minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')

    links = get_pending_event_task_links(db, window_start, window_end)
    assert len(links) == 0


def test_cleanup_old_event_task_links(db):
    from db.models import cleanup_old_event_task_links

    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO event_task_links "
        "(chat_id, event_id, task_id, event_summary, event_start_utc, task_title, notified, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (444, "evt_old", "tsk_old", "Old event", "2024-01-01T09:00:00Z", "Old task",
         (now - timedelta(days=10)).isoformat())
    )
    db.execute(
        "INSERT INTO event_task_links "
        "(chat_id, event_id, task_id, event_summary, event_start_utc, task_title, notified, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (444, "evt_new", "tsk_new", "New event", "2026-03-16T09:00:00Z", "New task",
         now.isoformat())
    )
    db.execute(
        "INSERT INTO event_task_links "
        "(chat_id, event_id, task_id, event_summary, event_start_utc, task_title, notified, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
        (444, "evt_unnotified_old", "tsk_u", "Unnotified old", "2024-01-01T09:00:00Z", "Un task",
         (now - timedelta(days=10)).isoformat())
    )
    db.commit()

    cleanup_old_event_task_links(db, days=7)

    remaining = db.execute(
        "SELECT event_id FROM event_task_links WHERE chat_id = 444"
    ).fetchall()
    event_ids = {r[0] for r in remaining}
    assert "evt_old" not in event_ids
    assert "evt_new" in event_ids
    assert "evt_unnotified_old" in event_ids  # un-notified rows must not be deleted


def test_mark_notified_empty_list_does_not_raise(db):
    from db.models import mark_event_task_links_notified
    # Should complete without raising any exception
    mark_event_task_links_notified(db, [])
