import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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


async def test_marks_notified_after_send(db):
    """After sending, links are marked notified and won't be sent again."""
    from db.models import add_event_task_link
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

    mock_bot.send_message.reset_mock()
    with patch("schedulers.event_task_notifier.get_conn", return_value=db), \
         patch("schedulers.event_task_notifier.list_connected_users", return_value=[111]), \
         patch("schedulers.event_task_notifier.get_setting", return_value="3"):
        await check_event_task_reminders(mock_bot)

    mock_bot.send_message.assert_not_called()


async def test_skips_disconnected_users(db):
    """Links for users not in list_connected_users are skipped."""
    from db.models import add_event_task_link
    from schedulers.event_task_notifier import check_event_task_reminders

    now = datetime.now(timezone.utc)
    event_start = (now + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%SZ')
    add_event_task_link(db, 999, "evt3", "tsk3", "Secret meeting", event_start, "Hidden task")

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    with patch("schedulers.event_task_notifier.get_conn", return_value=db), \
         patch("schedulers.event_task_notifier.list_connected_users", return_value=[111]), \
         patch("schedulers.event_task_notifier.get_setting", return_value="3"):
        await check_event_task_reminders(mock_bot)

    mock_bot.send_message.assert_not_called()


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

    assert mock_bot.send_message.call_count == 1
    text = mock_bot.send_message.call_args.kwargs["text"]
    assert "Buy materials" in text
    assert "Print handouts" in text


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

    assert send_call_count == 1
