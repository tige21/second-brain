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
