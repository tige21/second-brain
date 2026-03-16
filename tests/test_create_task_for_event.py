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
