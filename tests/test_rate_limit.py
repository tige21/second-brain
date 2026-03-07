import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123")
os.environ.setdefault("OPENAI_API_KEY", "x")

import time
import pytest
from unittest.mock import patch
from db.database import init_db
from db.models import update_rate_limit


@pytest.fixture
def conn(tmp_path):
    c = init_db(str(tmp_path / "test.db"))
    yield c
    c.close()


def check_rate_limit(conn, chat_id: int, limit_seconds: int = 5):
    """Extracted rate limit logic for testing."""
    from datetime import datetime, timezone
    from db.models import get_last_request_time
    last = get_last_request_time(conn, chat_id)
    if not last:
        return None
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    if elapsed < limit_seconds:
        return limit_seconds - elapsed
    return None


def test_first_request_always_allowed(conn):
    result = check_rate_limit(conn, chat_id=999)
    assert result is None


def test_immediate_second_request_blocked(conn):
    update_rate_limit(conn, 999)
    result = check_rate_limit(conn, chat_id=999, limit_seconds=5)
    assert result is not None
    assert result > 0


def test_wait_time_decreases_over_time(conn):
    update_rate_limit(conn, 999)
    wait1 = check_rate_limit(conn, chat_id=999, limit_seconds=5)
    time.sleep(0.1)
    wait2 = check_rate_limit(conn, chat_id=999, limit_seconds=5)
    assert wait1 > wait2


def test_request_allowed_after_limit_expires(conn):
    update_rate_limit(conn, 999)
    # Simulate time passing by using limit=0
    result = check_rate_limit(conn, chat_id=999, limit_seconds=0)
    assert result is None


def test_different_chat_ids_independent(conn):
    update_rate_limit(conn, 111)
    # chat 222 not rate limited
    result = check_rate_limit(conn, chat_id=222, limit_seconds=5)
    assert result is None
