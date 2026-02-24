import os
import pytest
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123")
os.environ.setdefault("OPENAI_API_KEY", "x")

from db.database import init_db


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    yield conn
    conn.close()


def test_init_creates_tables(db):
    cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "addresses" in tables
    assert "settings" in tables
    assert "notified_events" in tables
    assert "rate_limit" in tables
    assert "conversation_memory" in tables


def test_address_crud(db):
    from db.models import save_address, get_address, list_addresses, delete_address
    save_address(db, "дом", "ул. Тверская 1", "55.7558, 37.6173")
    addr = get_address(db, "дом")
    assert addr["address"] == "ул. Тверская 1"
    assert addr["coords"] == "55.7558, 37.6173"
    addresses = list_addresses(db)
    assert len(addresses) == 1
    delete_address(db, "дом")
    assert get_address(db, "дом") is None


def test_setting_crud(db):
    from db.models import set_setting, get_setting
    set_setting(db, "active_address", "дом")
    assert get_setting(db, "active_address") == "дом"
    set_setting(db, "active_address", "офис")
    assert get_setting(db, "active_address") == "офис"
    assert get_setting(db, "nonexistent") is None


def test_notified_events(db):
    from db.models import mark_notified, is_notified
    assert not is_notified(db, "event_123")
    mark_notified(db, "event_123")
    assert is_notified(db, "event_123")


def test_rate_limit(db):
    from db.models import update_rate_limit, get_last_request_time
    assert get_last_request_time(db, 12345) is None
    update_rate_limit(db, 12345)
    ts = get_last_request_time(db, 12345)
    assert ts is not None


def test_conversation_memory(db):
    from db.models import save_memory, load_memory
    messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    save_memory(db, 12345, messages)
    loaded = load_memory(db, 12345)
    assert len(loaded) == 2
    assert loaded[0]["content"] == "hello"
